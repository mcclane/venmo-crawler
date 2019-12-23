import sys
import os
import re
import json
import requests
import time
import argparse
from pprint import pprint
from pymongo import MongoClient, UpdateOne, InsertOne
from urllib.parse import urlencode, urlparse, parse_qs
from google_drive import get_venmo_code
from helpers import normalize_transaction

CREDENTIALS_FILE = "venmo_credentials.json"
AUTH_URL = "https://api.venmo.com/v1/oauth/authorize"
TWO_FACTOR_URL = "https://venmo.com/api/v5/two_factor/token"
TWO_FACTOR_AUTHORIZATION_URL = 'https://venmo.com/login'
FRIENDS_FEED_URL = "https://api.venmo.com/v1/stories/target-or-actor/friends"
PUBLIC_FEED_URL = "https://venmo.com/api/v5/public"
USER_FEED_URL = "https://venmo.com/api/v5/users/{}/feed"

AUTH_SUCCESS = "Nice."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', '--u', type=str)
    parser.add_argument('--password', '--p', type=str)
    parser.add_argument('--scrape-friends', '--sf', action='store_true')
    parser.add_argument('--before', '--b', type=str)
    parser.add_argument('--crawl-uncrawled', '--cu', action='store_true')
    parser.add_argument('--update-crawler-list', '--ucl', action='store_true')
    args = parser.parse_args()

    c = Crawler(args.username, args.password, CREDENTIALS_FILE)
    if args.scrape_friends:
        c.scrape_friends_feed()
    if args.update_crawler_list:
        c.update_crawler_list_from_transactions()
    if args.crawl_uncrawled:
        c.crawl_uncrawled_users()


class Crawler:
    def __init__(self, username=None, password=None, credentials_file=None):
        self.username = username
        self.password = password
        self.credentials_file = credentials_file

        self.v = Venmo(self.username, self.password, self.credentials_file)

        mdb_client = MongoClient("mongodb://127.0.0.1:27017")
        self.db = mdb_client.venmo

    def upsert_transaction_feed(self, feed):
        if not 'data' in feed:
            return None
        transactions = [t for t in feed['data']]
        normalized_transactions = transactions
        result = self.db.transactions.bulk_write([
            UpdateOne(t, {'$set': t}, upsert=True)
            for t in normalized_transactions
        ])
        return result

    def scrape_friends_feed(self, params=None, _next=None):
        feed = self.v.get_friends_feed(params=params, _next=_next)
        while feed != None and len(feed['data']) > 0:
            result = self.upsert_transaction_feed(feed)
            pprint(result.bulk_api_result)
            if result.bulk_api_result['nUpserted'] == 0:
                print("No more new transactions.")
                break

            time.sleep(5)
            feed = self.v.get_friends_feed(feed['pagination']['next'])

    def update_crawler_list_from_transactions(self):
        bulk_write = []
        for t in self.db.transactions.find():
            # Skip anything not a payment or of the unwanted friend feed structure
            if t['type'] != 'payment':
                continue
            target_entry = None
            actor_entry = None
            if 'app' in t:
                target_entry = {
                    'username': t['payment']['target']['user']['username'],
                    'display_name':
                    t['payment']['target']['user']['display_name'],
                }
                actor_entry = {
                    'username': t['payment']['actor']['username'],
                    'display_name': t['payment']['actor']['display_name'],
                }
            else:
                if type(t['transactions'][0]['target']) == dict:
                    target_entry = {
                        'username': t['transactions'][0]['target']['username'],
                        'display_name': t['transactions'][0]['target']['name'],
                        'venmo_id': t['transactions'][0]['target']['id'],
                    }
                actor_entry = {
                    'username': t['actor']['username'],
                    'display_name': t['actor']['name'],
                    'venmo_id': t['actor']['id'],
                }
            if target_entry != None:
                bulk_write.append(
                    UpdateOne(
                        {
                            'username': target_entry['username'],
                            'display_name': target_entry['display_name']
                        }, {'$set': target_entry},
                        upsert=True))
            if actor_entry != None:
                bulk_write.append(
                    UpdateOne(
                        {
                            'username': actor_entry['username'],
                            'display_name': actor_entry['display_name']
                        }, {'$set': actor_entry},
                        upsert=True))
        result = self.db.crawler.bulk_write(bulk_write)
        print(result.bulk_api_result['nUpserted'])

    def crawl_uncrawled_users(self):
        filt = {
            'last_crawled': {
                '$exists': False
            },
            'crawlable': {
                '$in': [None, True]
            },
        }
        if self.db.crawler.count_documents(filt) == 0:
            print("No uncrawled users")
            return

        print("Crawing uncrawled users:")
        uncrawled_users = self.db.crawler.find(filt).batch_size(3)
        for user in uncrawled_users:
            time.sleep(1)
            print(f"{user['display_name']} ({user['username']},",
                  end='',
                  flush=True)

            if 'venmo_id' in user and user['venmo_id'] != None and len(
                    user['venmo_id']) == 8:
                uid = user['venmo_id']
            else:
                uid = self.v.get_user_id_from_username(user['username'])
                if uid == None:
                    print("Couldn't find uid, marking as uncrawlable")
                    self.db.crawler.update_one(user,
                                               {'$set': {
                                                   'crawlable': False
                                               }})

                    continue
                self.db.crawler.update_one(user, {'$set': {'venmo_id': uid}})
            print(f"{uid}): ", end='', flush=True)
            feed = self.v.get_user_feed(uid)
            if feed == None:
                print("User feed was none")
            if len(feed['data']) == 0:
                print("No data, marking as uncrawlable")
                self.db.crawler.update_one(user,
                                           {'$set': {
                                               'crawlable': False
                                           }})
                continue

            res = self.db.crawler.update_one(
                user, {'$set': {
                    'last_crawled': time.time()
                }})
            while feed != None and len(feed['data']) > 0:
                updates = [
                    UpdateOne(transaction, {'$set': transaction}, upsert=True)
                    for transaction in feed['data']
                ]
                result = self.db.transactions.bulk_write(updates)
                if result.bulk_api_result['nUpserted'] == 0:
                    print("Already seen these transactions",
                          end='',
                          flush=True)
                    break
                print(f" +{result.bulk_api_result['nUpserted']}",
                      end='',
                      flush=True)
                if feed['paging']['next'] == None:
                    print("No next page", end='', flush=True)
                    break
                feed = self.v.get_user_feed(uid, _next=feed['paging']['next'])
                time.sleep(5)
            print(".")


class Venmo:
    def __init__(self, username=None, password=None, credentials_file=None):
        self.username = username
        self.password = password
        self.credentials_file = credentials_file
        if credentials_file == None:
            credentials_file = CREDENTIALS_FILE

        self.client = requests.session()
        self.client.headers[
            'User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36'

        if not os.path.exists(self.credentials_file):
            if self.username == None or self.password == None:
                raise Exception("Supply a username or password")

            if self.authenticate() != AUTH_SUCCESS:
                raise Exception("Auth unsuccessful")
        else:
            self.load_credentials()
            if not self.test_auth():
                self.authenticate()

    def authenticate(self):
        authorize_page = self.client.get(
            f"{AUTH_URL}?{urlencode({'client_id': 2667, 'scope': ' '.join(['access_profile', 'access_feed', 'access_friends'])})}"
        )
        auth_request = re.search('"auth_request" value="(\S+)"',
                                 str(authorize_page.content)).group(1)
        web_redirect_url = re.search('"web_redirect_url" value="(\S+)"',
                                     str(authorize_page.content)).group(1)
        c = self.client.cookies.get_dict()
        self.csrftoken2 = c['csrftoken2']
        data = {
            'username': self.username,
            'password': self.password,
            'csrftoken2': self.csrftoken2,
            'auth_request': auth_request,
            'web_redirect_url': web_redirect_url,
            'grant': 1
        }
        something = self.client.post(AUTH_URL,
                                     json=data,
                                     allow_redirects=False)
        redirect_url = something.headers['location']
        response = self.client.get(redirect_url)
        secret = re.search('"secret":"(\w*)"', str(response.content)).group(1)
        response = self.client.post(TWO_FACTOR_URL,
                                    headers={'Venmo-Otp-Secret': secret},
                                    json={
                                        'via': 'sms',
                                        'csrftoken2': self.csrftoken2
                                    })
        #verification_code = input("Verification code: ")
        sent_time = time.time() * 1000
        verification_code = None
        print("Checking Google Drive")
        while verification_code == None:
            verification_code = get_venmo_code(sent_time)
            print(".", end='', flush=True)
        print("Got the verification code:", verification_code)
        response = self.client.post(TWO_FACTOR_AUTHORIZATION_URL,
                                    json={
                                        'csrftoken2': self.csrftoken2,
                                        'return_json': 'true',
                                        'phoneEmailUsername': self.username,
                                        'password': self.password,
                                        'token': verification_code
                                    },
                                    allow_redirects=False)
        self.access_token = response.json()['access_token']
        self.client.cookies['api_access_token'] = self.access_token
        self.save_credentials()
        return AUTH_SUCCESS

    def get_friends_feed(self, params=None, _next=None):
        if params == None:
            params = {'limit': 50}
        if _next != None:
            response = self.client.get(_next)
        else:
            response = self.client.get(
                f"{FRIENDS_FEED_URL}?{urlencode(params)}")

        if response.status_code != 200:
            print(response, response.content)
            return None
        news = json.loads(response.content)
        return news

    def get_public_feed(self):
        response = self.client.get(PUBLIC_FEED_URL)
        if response.status_code != 200:
            print(response, response.content)
            return None
        news = json.loads(response.content)
        return news

    def get_user_feed(self, uid, params=None, _next=None):
        if params == None:
            params = {'limit': 50}
        url = f"{USER_FEED_URL.format(uid)}?{urlencode(params)}" if _next == None else _next
        response = self.client.get(url)
        if response.status_code != 200:
            print(response, response.content)
            return None
        response = json.loads(response.content)
        return response

    def get_user_id_from_username(self, username):
        req = requests.get(f"https://venmo.com/{username}")
        pat = f'"username": "{re.escape(username)}".*"user_id": ([0-9]+)'
        uid = re.search(pat, req.content.decode('utf-8'))
        if uid != None:
            return uid.group(1)

    def test_auth(self):
        req = self.client.get(FRIENDS_FEED_URL)
        if req.status_code != 200:
            print(req, req.content)
            return False
        return True

    def save_credentials(self):
        with open(self.credentials_file, "w") as f:
            f.write(
                json.dumps({
                    'username': self.username,
                    'password': self.password,
                    'access_token': self.access_token
                }))

    def load_credentials(self):
        with open(self.credentials_file, "r") as f:
            c = json.load(f)
            self.username = c['username']
            self.password = c['password']
            self.access_token = c['access_token']
        self.client.cookies['api_access_token'] = self.access_token


if __name__ == '__main__':
    main()
