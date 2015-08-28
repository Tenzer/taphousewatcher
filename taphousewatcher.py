#!/usr/bin/env python

import json
import unicodedata
from os import environ, path

import requests
from bs4 import BeautifulSoup
from twitter import OAuth, Twitter


TWITTER = None


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
    else:
        return True


def make_flag(country_code):
    result = ''
    for letter in country_code:
        result += unicodedata.lookup('REGIONAL INDICATOR SYMBOL LETTER {}'.format(letter))
    return result


def generate_tweet(beer):
    return 'New on tap {tap} | {name} | {alcohol} {type} | {brewery} | {country_flag} | {ratebeer_link}'.format(country_flag=make_flag(beer['country']), **beer)


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
            tweet_about_beer(beer, twitter)
        new_state.append(beer)

    if 'DEBUG' not in environ:
        write_file(new_state, path.join(script_folder, 'state.json'))
