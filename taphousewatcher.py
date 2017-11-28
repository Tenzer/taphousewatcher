#!/usr/bin/env python

import json
import smtplib
import unicodedata
from email.mime.text import MIMEText
from os import environ, path

import requests
from bs4 import BeautifulSoup
from twitter import OAuth, Twitter, TwitterHTTPError


def read_file(file_path):
    with open(file_path) as file_pointer:
        return json.load(file_pointer)


def write_file(content, file_path):
    with open(file_path, 'w') as file_pointer:
        json.dump(content, file_pointer)


def connect_twitter(config):
    return Twitter(auth=OAuth(**config['twitter']))


def get_taps(url):
    try:
        data = requests.get(url, headers={'User-Agent': 'Taphouse Watcher Bot (+https://twitter.com/TaphouseWatcher)'}).json()
    except (requests.RequestException, json.JSONDecodeError):
        # There's no real error handling here, we just give up in case we can't contact the site
        exit()

    for tap, beer in data.items():
        if not beer:
            # An empty tap
            yield tap, {}
            continue

        yield tap, {
            'tap': tap,
            'id': beer.get('kegId'),
            'name': beer.get('beverage'),
            'type': beer.get('beverageType'),
            'brewery': beer.get('company'),
            'country': beer.get('country'),
            'alcohol': beer.get('abv'),
            'ratebeer_id': beer.get('ratebeerId'),
            'christmas': beer.get('xmas'),
        }


def get_rating(beer_id):
    try:
        html = requests.get(
            'http://www.ratebeer.com/Ratings/Beer/Beer-Ratings.asp?BeerID={}'.format(beer_id),
            headers={'User-Agent': 'Taphouse Watcher Bot (+https://twitter.com/TaphouseWatcher)'}
        ).text
    except requests.RequestException:
        return None

    soup = BeautifulSoup(html, 'html.parser')
    rating = soup.find('div', class_='ratingValue')

    if not rating:
        return None

    return int(rating.get_text())


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

    if beer['christmas']:
        beer['type'] = '{} {}'.format(unicodedata.lookup('CHRISTMAS TREE'), beer['type'])

    tweet = 'New on tap {tap} | {name} | {alcohol}% {type} | {brewery} | {country_flag} | RateBeer: {rating_text}'.format(**beer)
    if len(tweet) <= 280:
        return tweet

    # We have to trim some of the fat, let's start with the brewery
    tweet = 'New on tap {tap} | {name} | {alcohol}% {type} | {country_flag} | RateBeer: {rating_text}'.format(**beer)
    if len(tweet) <= 280:
        return tweet

    # Try to just cut off some minor bits then
    tweet = 'Tap {tap} | {name} | {alcohol}% {type} | {country_flag} | RB: {rating_text}'.format(**beer)
    if len(tweet) <= 280:
        return tweet

    # We have to take more drastic measures now
    tweet = 'Tap {tap} | {name_short}{ellipsis} | {alcohol}% {type_short}{ellipsis} | {country_flag} | RB: {rating_text}'.format(
        name_short=beer['name'][:70].strip(),
        type_short=beer['type'][:30].strip(),
        ellipsis=unicodedata.lookup('HORIZONTAL ELLIPSIS'),
        **beer
    )
    if len(tweet) <= 280:
        return tweet
    else:
        # Give up, something has to be totally off
        print('Could not generate a short enough tweet based on this beer:', beer)
        exit(1)


def tweet_about_beer(beer, twitter, config):
    try:
        if config.get('geo', {}).get('enabled', False):
            twitter.statuses.update(
                status=generate_tweet(beer),
                lat=config['geo'].get('lat'),
                long=config['geo'].get('long'),
                display_coordinates=True,
            )
        else:
            twitter.statuses.update(status=generate_tweet(beer))
    except TwitterHTTPError:
        pass


def possibly_mail_alert(config, failed):
    if 'email' not in config or not config['email'].get('recipient') or failed != config['email'].get('threshold'):
        return

    message = MIMEText('Failed to get RateBeer rating for the last {} beers!'.format(failed))
    message['Subject'] = 'Alert from Taphouse Watcher'
    message['From'] = 'TaphouseWatcher'
    message['To'] = config['email']['recipient']

    smtp = smtplib.SMTP()
    smtp.connect()
    smtp.send_message(message)
    smtp.quit()


if __name__ == '__main__':
    script_folder = path.dirname(__file__)
    config = read_file(path.join(script_folder, 'config.json'))
    previous_state = read_file(path.join(script_folder, 'state.json'))
    twitter = connect_twitter(config)

    new_state = {}
    failed_ratings = previous_state['failed_ratings']
    for tap, beer in get_taps('http://taphouse.dk/api/taplist/'):
        if not beer:
            new_state[tap] = previous_state['beers'].get(tap, {})
            continue

        if beer['id'] != previous_state['beers'].get(tap, {}).get('id'):
            beer['rating'] = get_rating(beer['ratebeer_id'])
            tweet_about_beer(beer, twitter, config)

            if beer['rating']:
                failed_ratings = 0
            else:
                failed_ratings += 1
                possibly_mail_alert(config, failed_ratings)

        new_state[tap] = beer

    if 'DEBUG' not in environ:
        payload = {
            'failed_ratings': failed_ratings,
            'beers': new_state,
        }
        write_file(payload, path.join(script_folder, 'state.json'))
