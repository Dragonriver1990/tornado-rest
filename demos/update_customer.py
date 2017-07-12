#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import sys

if sys.version_info > (3,):
    raw_input = input
    import http.client as httplib
    import urllib.parse as urllib
else:
    import httplib
    import urllib

print('Update customer')
print('===============')
id_customer = raw_input('Id Customer      : ')
name_customer = raw_input('Customer Name    : ')
address_customer = raw_input('Customer Address : ')

if len(id_customer) == 0 and len(name_customer) == 0 and len(address_customer) == 0:
    print('You must indicates id, name and address of customer')
else:
    params = urllib.urlencode({'name_customer': str(name_customer), 'address_customer': str(address_customer)})
    headers = {"Content-type": "application/x-www-form-urlencoded"}
    conn = httplib.HTTPConnection("localhost:8080")

    conn.request('PUT', '/customer/%s' % id_customer, params, headers)

    resp = conn.getresponse()
    data = resp.read()
    if resp.status == 200:
        json_data = json.loads(data.decode('utf-8'))
        print(json_data)
    else:
        print(data.decode('utf-8'))
