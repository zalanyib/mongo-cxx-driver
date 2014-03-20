#!/usr/bin/python

import xml.sax
import requests
import json
import re

class MyContentHandler(xml.sax.ContentHandler):
    def __init__(self):
        xml.sax.ContentHandler.__init__(self)
        self.files = []
        self.file = {}
        self.in_file = False
        self.coverage = {}
        self.highest = 0

    def startElement(self, name, attrs):
        if (name == 'class'):
            fname = attrs["filename"]

            if (re.search('src/mongo', fname)):
                self.coverage = {}
                self.highest = 0
                self.in_file = True
                self.file = {
                    "name"     : fname,
                    "source"   : open(fname).read(),
                }

        elif (self.in_file and name == 'line'):
            y = int(attrs["number"])
            self.highest = y
            self.coverage[y] = attrs["hits"]
    
    def endElement(self, name):
        if (name == 'class' and self.in_file):
            self.file["coverage"] = []
            for x in xrange(1, self.highest + 1):
                self.file["coverage"].append(self.coverage.get(x))
            self.files.append(self.file)
            self.in_file = False

def main(source_file):
    source = open(source_file)
    mch = MyContentHandler()
    xml.sax.parse(source, mch)

    payload = json.dumps({
        "service_job_id" : "gcovr",
        "service_name"   : "meh",
#        "repo_token"     : "Your token",
        "source_files"   : mch.files,
    })

    r = requests.post("https://coveralls.io/api/v1/jobs", files={'json_file': payload})
    print r.text

if __name__ == "__main__":
    main("out.xml")
