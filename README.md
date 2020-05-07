Crawls user feeds and puts the transactions into a mongodb database. Used to scrape 1 million transactions so far.

## Requirements
python3

a mongodb server

Python packages: `requests google-api-python-client pymongo`

## Usage
Scrape transactions from your friends feed
`python3 venmo.py --username foo --password bar --scrape-friends`

Put users found in your friends feed into the crawler's database (list of people to crawl) (uses credentials saved to a file)
`python3 venmo.py --update-crawler-list`

Crawl uncrawled users found in the crawler database
`python3 venmo.py --crawl-uncrawled`

## Authentication:
The venmo API requires 2FA when signing in. Could be done manually, but I have [Join](https://joaoapps.com/join/), so the program checks google drive for texts uploaded by Join for the 2FA code.

Login and password are stored in a local json file along with the most recent API access token.

## To start mongodb manually
`mongod --config /usr/local/etc/mongod.conf --fork`

