import sys
import os
import re
import json
import requests
import time
from pprint import pprint
from pymongo import MongoClient
from pymongo import UpdateOne
from urllib.parse import urlencode, urlparse, parse_qs
from google_drive import get_venmo_code
import argparse

CREDENTIALS_FILE = os.path.expanduser('~/.venmo_credentials.json')
AUTH_URL = "https://api.venmo.com/v1/oauth/authorize"
TWO_FACTOR_URL = "https://venmo.com/api/v5/two_factor/token"
TWO_FACTOR_AUTHORIZATION_URL = 'https://venmo.com/login'
FRIENDS_FEED_URL = "https://api.venmo.com/v1/stories/target-or-actor/friends"
PUBLIC_FEED_URL = "https://venmo.com/api/v5/public"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', '--u', type=str)
    parser.add_argument('--password', '--p', type=str)
    parser.add_argument('--before', '--b', type=str)
    args = parser.parse_args()

    if os.path.exists(CREDENTIALS_FILE
                      ) and args.username == None and args.password == None:
        credentials = load_credentials()
        username = credentials['username']
        password = credentials['password']
    else:
        print("No supplied username or password")
        return

    client = requests.session()
    client.headers[
        'User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36'

    if not os.path.exists(CREDENTIALS_FILE):
        authenticate(client, username, password)
    else:
        print("using saved credentials")

    if not os.path.exists(CREDENTIALS_FILE):
        print("apparently authentication was unsuccessful")
        return

    params = None
    if args.before != None:
        print("using before id", args.before)
        params = {'limit': 50, 'before_id': args.before}

    credentials = load_credentials()
    news = get_news(client, credentials['access_token'], params=params)
    if news == None:
        authenticate(client, username, password)
        credentials = load_credentials()
        news = get_news(client, credentials['access_token'], params=params)
        if news == None:
            print("Something has gone very wrong")
            return

    mdb_client = MongoClient("mongodb://127.0.0.1:27017")
    db = mdb_client.venmo
    while news != None:
        result = db.transactions.bulk_write([
            UpdateOne(transaction, {'$set': transaction}, upsert=True)
            for transaction in news['data']
        ])
        pprint(result.bulk_api_result)

        next_query = urlparse(news['pagination']['next']).query
        next_query = parse_qs(next_query)
        if 'before_id' in next_query:
            params = {'limit': 50, 'before_id': next_query['before_id'][0]}
            print(params)
        else:
            print("No next in query!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            print(news['pagination'])
            break
        news = get_news(client, credentials['access_token'], params=params)
        print(news['data'][0])
        time.sleep(5)


def get_public_feed(client, access_token):
    cookies = {'api_access_token': access_token}
    response = requests.get(f"{FRIENDS_FEED_URL}?{urlencode(params)}",
                            cookies=cookies)
    print(response)
    if response.status_code != 200:
        print(response.content)
        return None
    news = json.loads(response.content)
    return news


def get_news(client, access_token, params=None):
    if params == None:
        params = {'limit': 35}
    cookies = {'api_access_token': access_token}
    response = requests.get(f"{FRIENDS_FEED_URL}?{urlencode(params)}",
                            cookies=cookies)
    print(response)
    if response.status_code != 200:
        print(response.content)
        return None
    news = json.loads(response.content)
    return news


def load_credentials():
    with open(CREDENTIALS_FILE, 'r') as f:
        return json.load(f)


def authenticate(client, username, password):
    authorize_page = client.get(
        f"{AUTH_URL}?{urlencode({'client_id': 2667, 'scope': ' '.join(['access_profile', 'access_feed', 'access_friends'])})}"
    )
    auth_request = re.search('"auth_request" value="(\S+)"',
                             str(authorize_page.content)).group(1)
    web_redirect_url = re.search('"web_redirect_url" value="(\S+)"',
                                 str(authorize_page.content)).group(1)
    c = client.cookies.get_dict()
    data = {
        'username': username,
        'password': password,
        'csrftoken2': c['csrftoken2'],
        'auth_request': auth_request,
        'web_redirect_url': web_redirect_url,
        'grant': 1
    }
    something = client.post(AUTH_URL, json=data, allow_redirects=False)
    redirect_url = something.headers['location']
    response = client.get(redirect_url)
    print(response)
    secret = re.search('"secret":"(\w*)"', str(response.content)).group(1)
    print(secret)
    response = client.post(TWO_FACTOR_URL,
                           headers={'Venmo-Otp-Secret': secret},
                           json={
                               'via': 'sms',
                               'csrftoken2': c['csrftoken2']
                           })
    print(response)
    print(response.content)
    #verification_code = input("Verification code: ")
    sent_time = time.time() * 1000
    verification_code = None
    print("Checking google drive for verification code")
    while verification_code == None:
        verification_code = get_venmo_code(sent_time)
        print(".", end='')
    print("Got the verification code:", verification_code)
    response = client.post(TWO_FACTOR_AUTHORIZATION_URL,
                           json={
                               'csrftoken2': c['csrftoken2'],
                               'return_json': 'true',
                               'phoneEmailUsername': username,
                               'password': password,
                               'token': verification_code
                           },
                           allow_redirects=False)
    access_token = response.json()['access_token']
    with open(CREDENTIALS_FILE, "w") as f:
        f.write(
            json.dumps({
                'username': username,
                'password': password,
                'access_token': access_token
            }))


if __name__ == '__main__':
    main()
