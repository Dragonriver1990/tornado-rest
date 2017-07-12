#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import sys

if sys.version_info > (3,):
    raw_input = input
    import http.client as httplib
else:
    import httplib

print('Delete customer')
print('===============')
id_customer = raw_input('Id Customer      : ')

if len(id_customer) == 0:
    print('You must indicates id of customer')
else:
    conn = httplib.HTTPConnection("localhost:8081")

    conn.request('DELETE', '/customer/%s' % id_customer)

    resp = conn.getresponse()
    data = resp.read()
    if resp.status == 200:
        json_data = json.loads(data.decode('utf-8'))
        print(json_data)
    else:
        print(data.decode('utf-8'))
