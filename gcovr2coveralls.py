#!/usr/bin/python

import argparse
import xml.sax
import requests
import json
import re
import os
import sys
import subprocess

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

class GitRepo():
    def __init__(self, directory):
        self.dir = directory

    def git(self, *arguments):
        proc = subprocess.Popen(['git'] + list(arguments),
               stdout=subprocess.PIPE, cwd=self.dir)

        return proc.communicate()[0].decode('UTF-8')

def gitrepo(directory):
    repo = GitRepo(directory)

    log = repo.git("--no-pager", "log", "-1", "--pretty=format:%H\n%aN\n%ae\n%cN\n%ce\n%s").split("\n")

    remotes = []

    for line in repo.git('remote', '-v').split("\n"):
        if ('(fetch)' in line):
            remotes.append( { 'name' : line.split()[0], 'url' : line.split()[1] } )

    return {
        'head' : {
            'id'             : log[0],
            'author_name'    : log[1],
            'author_email'   : log[2],
            'commiter_name'  : log[3],
            'commiter_email' : log[4],
            'message'        : log[5],
         },
        'branch': repo.git('rev-parse', '--abbrev-ref', 'HEAD').strip(),
        'remotes' : remotes,
    }

class CoverageFile():
    def __init__(self, name, line_rate):
        self.name = name
        self.sparse = {}
        self.highest = 0
        self.line_rate = line_rate

    def add_hit(self, num, hit):
        self.highest = int(num)
        self.sparse[int(num)] = int(hit)

    def get_dense(self):
        return [self.sparse.get(x) for x in xrange(1, self.highest)]

class MyContentHandler(xml.sax.ContentHandler):
    def __init__(self, args):
        xml.sax.ContentHandler.__init__(self)
        self.files = []
        self.in_file = False
        self.args = args

        self.re = re.compile("^{}(.*{}.*)$".format(args.root, args.filter))

    def startElement(self, name, attrs):
        if (name == 'class'):
            fname = attrs["filename"]
            m = self.re.match(fname)

            if (m):
                fname = m.group(1)
                self.file = CoverageFile(fname, attrs["line-rate"])
                self.in_file = True

        elif (self.in_file and name == 'line'):
            self.file.add_hit(attrs["number"], attrs["hits"])
    
    def endElement(self, name):
        if (self.in_file and name == 'class'):
            self.files.append(self.file)
            self.in_file = False

def parse_args():
    parser = argparse.ArgumentParser(description='cobertura coverage shim')
    parser.add_argument('--type', required=True, help="output type", choices= [
        "cobertura",
        "coveralls_json",
        "coveralls",
        "summary",
    ])
    parser.add_argument('--root', help="Root of interesting files")
    parser.add_argument('--filter', help="Filter for interesting files", default="")
    parser.add_argument('--output', type=argparse.FileType('w'), default=sys.stdout, help="output file")
    parser.add_argument('input', help="Cobertura XML coverage", metavar="input.xml")
    parser.add_argument('--coveralls-repo-token', help="Coveralls repo token", metavar="token", dest="coveralls_repo_token")
    parser.add_argument('--git', help="Git repo", metavar="repo")

    args = parser.parse_args()

    if (args.type == 'coveralls'):
        args.travis_job_id = os.environ.get('TRAVIS_JOB_ID')

        if (not args.coveralls_repo_token and not args.travis_job_id):
            parser.error("Can't upload to coveralls without a coveralls-repo-token or travis job id")

    if (args.root is None):
        args.root = os.getcwd()

    args.root = os.path.abspath(args.root)

    if (args.root != '/'):
        args.root += '/'

    return args

def parse_xml(args):
    source = open(args.input)
    mch = MyContentHandler(args)
    xml.sax.parse(source, mch)
    return mch.files

def output_travis_json(args):
    coverage = parse_xml(args)

    files = []
    for v in coverage:
        files.append({
            "name"     : v.name,
            "coverage" : v.get_dense(),
            "source"   : open(os.path.join(args.root, v.name)).read(),
        })

    payload = {
        "source_files" : files,
    }

    if (args.git):
        payload["git"] = gitrepo(args.git)

    if (args.coveralls_repo_token):
        payload["service_name"] = "cobertura2coveralls"
        payload["repo_token"] = args.coveralls_repo_token
    else:
        payload["service_name"] = "travis-ci"
        payload["service_job_id"] = args.travis_job_id

    return json.dumps(payload)

def upload_travis(args):
    payload = output_travis_json(args)

    r = requests.post("https://coveralls.io/api/v1/jobs", files={'json_file': payload})
    return r.text

def output_summary(args):
    coverage = parse_xml(args)

    return "\n".join(
        [ "\t".join([x.name, x.line_rate]) for x in coverage ]
    )

def output_cobertura(args):
    tree = ET.ElementTree(file=args.input)

    cre = re.compile("^{}(.*{}.*)$".format(args.root, args.filter))

    packages = tree.find('packages')

    to_drop = []

    for package in tree.iter(tag='package'):
        c = package.find('classes')
        drop = False
        for elem in c.findall('class'):
            m = cre.match(elem.attrib["filename"])
            if (m):
                elem.set("filename", m.group(1))
            else:
                to_drop.append(package)
                break

    for package in to_drop:
        packages.remove(package)

    return ET.tostring(tree.getroot(), encoding='utf8', method='xml')

def main():
    args = parse_args()

    args.output.write({
        "cobertura"      : output_cobertura,
        "coveralls"      : upload_travis,
        "coveralls_json" : output_travis_json,
        "summary"        : output_summary,
    }[args.type](args) + "\n")

if __name__ == "__main__":
    main()
