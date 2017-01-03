"""
This python script queries all available executions of a jenkins job
and collects information on whether or not the job passed or failed,
and what caused the job to fail.

Required environment variables:
    JENKINS_PROJECT_PATH - A url path to a jenkins project.
        (ex: https://jenkins-server.com/job/job-name/)
    JENKINS_USER - The username of a jenkins user.
    JENKINS_API_TOKEN - The api token for the jenkins user.
"""

import os
import re
import json
import requests
from requests.auth import HTTPBasicAuth

JENKINS_PROJECT_PATH = os.environ['JENKINS_PROJECT_PATH']
JENKINS_USER = os.environ['JENKINS_USER']
JENKINS_API_TOKEN = os.environ['JENKINS_API_TOKEN']

CACHE_FILE = 'cache.txt'

def get(url):
    '''Send a request to a url and retry if the connection times out'''
    auth = HTTPBasicAuth(JENKINS_USER, JENKINS_API_TOKEN)
    for i in range(5):
        try:
            res = requests.get(url, auth=auth, timeout=5)
        except Exception:
            print("Connection timed out, trying again")
            continue
        break
    if res.status_code is 200:
        return res
    else:
        return None

def load_from_cache(filepath):
    if os.path.isfile(filepath):
        with open(CACHE_FILE, 'r') as file:
            return json.loads(file.read())
    return {}

def save_cache(data, filepath):
    with open(CACHE_FILE, 'w') as file:
        file.write(json.dumps(data))


if __name__ == '__main__':
    cache = load_from_cache(CACHE_FILE)

    # Find the first and last builds for the job.
    project_url = "{}/api/json".format(JENKINS_PROJECT_PATH)
    res = get(project_url).json()
    first_build = int(res['firstBuild']['number'])
    last_build = int(res['lastCompletedBuild']['number'])

    matcher = re.compile(
        'GitHub pull request #(\d+) of commit ([0-9a-z]+),')
    error_matcher = re.compile(
        'builder for .\/opt\/ns\/nix\/store\/[a-z0-9]+-(\S+). failed')

    for job in range(first_build, last_build+1):
        if str(job) in cache:
            continue

        print('Querying execution #', job)

        job_url = ("{}/{}/api/json".format(JENKINS_PROJECT_PATH, job))
        res = get(job_url).json()

        if res is None or res['building']:
            continue

        for action in res['actions']:
            if action.get('_class') == 'hudson.model.CauseAction':
                description = action['causes'][0]['shortDescription']
                match = matcher.search(description)
                if match is not None:
                    pull_request_id = match.group(1)
                    commit_hash = match.group(2)
                break

        job_data = {
            'commit_hash': commit_hash,
            'pull_request_id': pull_request_id,
            'result': res['result'],
            'timestamp': res['timestamp']
        }

        if res['result'] == 'FAILURE':
            url = ("{}/{}/console".format(JENKINS_PROJECT_PATH, job))
            output = get(url).text
            match = error_matcher.search(output)
            if match is None:
                print('Unable to find cause of failure for job')
            else:
                job_data['cause'] = match.group(1)

        cache[job] = job_data

    save_cache(cache, CACHE_FILE)
