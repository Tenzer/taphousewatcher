#!/usr/bin/env python

import json
import unicodedata
from os import environ, path

import requests
from bs4 import BeautifulSoup
from twitter import OAuth, Twitter


def read_file(file_path):
    with open(file_path) as file_pointer:
        return json.load(file_pointer)


def write_file(content, file_path):
    with open(file_path, 'w') as file_pointer:
        json.dump(content, file_pointer)


def connect_twitter(config):
    return Twitter(auth=OAuth(**config['twitter']))


def scrape(url):
    html = requests.get(url, headers={'User-Agent': 'Taphouse Watcher Bot (+https://twitter.com/TaphouseWatcher)'}).text
    soup = BeautifulSoup(html, 'html.parser')
    beer_table = soup.find('table', id='beerTable').tbody

    for beer in beer_table.find_all('tr'):
        attributes = beer.find_all('td')
        if len(attributes) <= 1:
            # Propably an empty tap
            continue

        yield {
            'tap': attributes[0].get_text(),
            'name': attributes[1].get_text().strip(),
            'type': attributes[2].get_text(),
            'brewery': attributes[3].get_text(),
            'country': attributes[4].get_text(),
            'alcohol': attributes[5].get_text(),
            'ratebeer_link': attributes[8].a['href'],
        }


def is_new_beer(new_beer, previous_state):
    for beer in previous_state:
        if new_beer['name'] == beer['name']:
            return False

    return True


def get_rating(url):
    html = requests.get(url, headers={'User-Agent': 'Taphouse Watcher Bot (+https://twitter.com/TaphouseWatcher)'}).text
    soup = BeautifulSoup(html, 'html.parser')
    rating_block = soup.find('span', itemprop='rating')

    if not rating_block:
        print('The beer does not have any rating')
        return None

    for span in rating_block.find_all('span'):
        if not span.attrs:
            # The <span> we are looking for doesn't have any attributes
            return span.get_text()

    # Safety net
    return None


def make_flag(country_code):
    country_code = country_code.upper()

    if country_code == 'UK':
        # UK is not part of the ISO 3166-1 standard
        country_code = 'GB'

    result = ''
    for letter in country_code[:2]:
        result += unicodedata.lookup('REGIONAL INDICATOR SYMBOL LETTER {}'.format(letter))
    return result


def generate_tweet(beer):
    if beer['rating']:
        rating_text = ' | RateBeer: {}'.format(beer['rating'])

        if int(beer['rating']) >= 95:
            rating_text += ' {}'.format(unicodedata.lookup('GLOWING STAR'))
    else:
        rating_text = ''

    return 'New on tap {tap} | {name} | {alcohol} {type} | {brewery} | {country_flag}{rating_text}'.format(
        country_flag=make_flag(beer['country']),
        rating_text=rating_text,
        **beer
    )


def tweet_about_beer(beer, twitter):
    twitter.statuses.update(status=generate_tweet(beer))


if __name__ == '__main__':
    script_folder = path.dirname(__file__)
    config = read_file(path.join(script_folder, 'config.json'))
    previous_state = read_file(path.join(script_folder, 'state.json'))
    twitter = connect_twitter(config)

    new_state = []
    for beer in scrape('http://taphouse.dk/'):
        if is_new_beer(beer, previous_state):
            beer['rating'] = get_rating(beer['ratebeer_link'])
            tweet_about_beer(beer, twitter)

        new_state.append(beer)

    if 'DEBUG' not in environ:
        write_file(new_state, path.join(script_folder, 'state.json'))
