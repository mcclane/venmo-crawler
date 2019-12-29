from functools import reduce
from pprint import pprint
import operator


def get_by_path(root, items):
    """Access a nested object in root by item sequence."""
    return reduce(operator.getitem, items, root)


def set_by_path(root, items, value):
    """Set a value in a nested object in root by item sequence."""
    get_by_path(root, items[:-1])[items[-1]] = value


# Transactions need to be done manually
EMPTY_DICT = 5
a = 'actor'
ap = 'payment.actor'
normalize_mapping = {
    a + '.firstname': ap + '.first_name',
    a + '.lasttname': ap + '.last_name',
    a + '.picture': ap + '.profile_picture_url',
    a + '.is_blocked': ap + '.is_blocked',
    a + '.date_created': ap + '.date_joined',
    a + '.external_id': ap + '.id',
    'audience': 'audience',
    'comments': 'comments.data',
    'created_time': 'date_created',
    'updated_time': 'date_updated',
    'likes': 'likes',
    'mentions': 'mentions.data',
    'message': 'note',
    'type': 'type',
}


def normalize_transaction(t):
    if not ('app' in t):
        # Already in the format we want
        return t
    nt = {"actor": {}}
    for k in normalize_mapping:
        path = normalize_mapping[k]
        if path == None:
            v = None
        elif path == EMPTY_DICT:
            v = {}
        else:
            v = get_by_path(t, path.split('.'))
        set_by_path(nt, k.split('.'), v)

    nt['transactions'] = [{
        "target": {
            "username": t['payment']['target']['user']['username'],
            "picture": t['payment']['target']['user']['profile_picture_url'],
            "name": t['payment']['target']['user']['display_name'],
            "firstname": t['payment']['target']['user']['first_name'],
            "lastname": t['payment']['target']['user']['last_name'],
            "date_created": t['payment']['target']['user']['date_joined'],
            "external_id": t['payment']['target']['user']['id'],
            "id": None
        }
    }]
    return nt


"""
test = {	"app" : {
		"description" : "Venmo for iPhone",
		"site_url" : None,
		"image_url" : "https://venmo.s3.amazonaws.com/oauth/no-image-100x100.png",
		"id" : 1,
		"name" : "Venmo for iPhone"
	},
	"audience" : "public",
	"authorization" : None,
	"comments" : {
		"count" : 0,
		"data" : [ ]
	},
	"date_created" : "2019-12-10T02:53:33",
	"date_updated" : "2019-12-10T02:53:33",
	"id" : "2895566402280751953",
	"likes" : {
		"count" : 0,
		"data" : [ ]
	},
	"mentions" : {
		"count" : 0,
		"data" : [ ]
	},
	"note" : "S",
	"payment" : {
		"status" : "settled",
		"id" : "2895566401618051718",
		"date_authorized" : None,
		"merchant_split_purchase" : None,
		"date_completed" : "2019-12-10T02:53:33",
		"target" : {
			"merchant" : None,
			"redeemable_target" : None,
			"phone" : None,
			"user" : {
				"username" : "seanchang36",
				"last_name" : "Chang",
				"friends_count" : None,
				"is_group" : False,
				"is_active" : True,
				"trust_request" : None,
				"phone" : None,
				"profile_picture_url" : "https://pics.venmo.com/593020af-655b-4705-b86d-b01c297e023a?width=460&height=460&photoVersion=1",
				"is_blocked" : False,
				"id" : "2565785755058176133",
				"identity" : None,
				"date_joined" : "2018-09-11T02:38:17",
				"about" : " ",
				"display_name" : "Sean Chang",
				"first_name" : "Sean",
				"friend_status" : "not_friend",
				"email" : None
			},
			"type" : "user",
			"email" : None
		},
		"audience" : "public",
		"actor" : {
			"username" : "Chris-Keeley-5",
			"last_name" : "Keeley",
			"friends_count" : None,
			"is_group" : False,
			"is_active" : True,
			"trust_request" : None,
			"phone" : None,
			"profile_picture_url" : "https://pics.venmo.com/c941476b-9563-4bf1-a61d-4d4153d96ed6?width=50&height=50&photoVersion=1&facebook=True",
			"is_blocked" : False,
			"id" : "2586823620558848487",
			"identity" : None,
			"date_joined" : "2018-10-10T03:16:46",
			"about" : " ",
			"display_name" : "Chris Keeley",
			"first_name" : "Chris",
			"friend_status" : "friend",
			"email" : None
		},
		"note" : "S",
		"amount" : None,
		"action" : "pay",
		"date_created" : "2019-12-10T02:53:33",
		"date_reminded" : None
	},
	"transfer" : None,
	"type" : "payment"
}
pprint(normalize_transaction(test))
"""