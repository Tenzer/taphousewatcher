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
    rating_block = soup.find('span', string='overall')

    if not rating_block:
        return None

    return int(rating_block.nextSibling.get_text())


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
        beer['rating_text'] = str(beer['rating'])

        if beer['rating'] >= 95:
            beer['rating_text'] += ' {}'.format(unicodedata.lookup('GLOWING STAR'))
    else:
        beer['rating_text'] = 'N/A'

    beer['country_flag'] = make_flag(beer['country'])

    tweet = 'New on tap {tap} | {name} | {alcohol} {type} | {brewery} | {country_flag} | RateBeer: {rating_text}'.format(**beer)
    if len(tweet) <= 140:
        return tweet

    # We have to trim some of the fat, let's start with the brewery
    tweet = 'New on tap {tap} | {name} | {alcohol} {type} | {country_flag} | RateBeer: {rating_text}'.format(**beer)
    if len(tweet) <= 140:
        return tweet

    # Try to just cut off some minor bits then
    tweet = 'Tap {tap} | {name} | {alcohol} {type} | {country_flag} | RB: {rating_text}'.format(**beer)
    if len(tweet) <= 140:
        return tweet

    # We have to take more drastic measures now
    tweet = 'Tap {tap} | {name_short}{ellipsis} | {alcohol} {type_short}{ellipsis} | {country_flag} | RB: {rating_text}'.format(
        name_short=beer['name'][:70].strip(),
        type_short=beer['type'][:30].strip(),
        ellipsis=unicodedata.lookup('HORIZONTAL ELLIPSIS'),
        **beer
    )
    if len(tweet) <= 140:
        return tweet
    else:
        # Give up, something has to be totally off
        print('Could not generate a short enough tweet based on this beer:', beer)
        exit(1)


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
