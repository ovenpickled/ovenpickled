import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time
import hashlib

# Fine-grained personal access token with All Repositories access:
# Account permissions: read:Followers, read:Starring, read:Watching
# Repository permissions: read:Commit statuses, read:Contents, read:Issues, read:Metadata, read:Pull Requests
HEADERS = {'authorization': 'token '+ os.environ['ACCESS_TOKEN']}
USER_NAME = os.environ['USER_NAME'] # 'ovenpickled'
QUERY_COUNT = {'user_getter': 0, 'follower_getter': 0, 'graph_repos_stars': 0, 'recursive_loc': 0, 'graph_commits': 0, 'loc_query': 0}


def daily_readme(birthday):
    """
    Returns the length of time since I was born
    e.g. 'XX years, XX months, XX days'
    """
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return '{} {}, {} {}, {} {}{}'.format(
        diff.years, 'year' + format_plural(diff.years), 
        diff.months, 'month' + format_plural(diff.months), 
        diff.days, 'day' + format_plural(diff.days),
        ' 🎂' if (diff.months == 0 and diff.days == 0) else '')


def format_plural(unit):
    """
    Returns a properly formatted number
    e.g.
    'day' + format_plural(diff.days) == 5
    >>> '5 days'
    'day' + format_plural(diff.days) == 1
    >>> '1 day'
    """
    return 's' if unit != 1 else ''


def simple_request(func_name, query, variables):
    """
    Returns a request, or raises an Exception if the response does not succeed.
    """
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS)
    if request.status_code == 200:
        return request
    raise Exception(func_name, ' has failed with a', request.status_code, request.text, QUERY_COUNT)


def graph_commits(start_date, end_date):
    """
    Uses GitHub's GraphQL v4 API to return total commit count
    """
    query = '''
    query($start_date: DateTime!, $end_date: DateTime!, $login: String!) {
        user(login: $login) {
            contributionsCollection(from: $start_date, to: $end_date) {
                contributionCalendar {
                    totalContributions
                }
            }
        }
    }'''
    variables = {'start_date': start_date,'end_date': end_date, 'login': USER_NAME}
    request = simple_request(graph_commits.__name__, query, variables)
    return int(request.json()['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions'])


def graph_repos_stars(count_type, owner_affiliation):
    """
    Uses GitHub's GraphQL v4 API to return repository or star count.
    """
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!) {
        user(login: $login) {
            repositories(first: 100, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers {
                                totalCount
                            }
                        }
                    }
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME}
    request = simple_request(graph_repos_stars.__name__, query, variables)
    if request.status_code == 200:
        if count_type == 'repos':
            return request.json()['data']['user']['repositories']['totalCount']
        elif count_type == 'stars':
            return sum([repo['node']['stargazers']['totalCount'] for repo in request.json()['data']['user']['repositories']['edges']])


def user_getter():
    """
    Uses GitHub's GraphQL v4 API to get user data (followers, following, etc.)
    """
    query = '''
    query($login: String!) {
        user(login: $login) {
            followers {
                totalCount
            }
            following {
                totalCount
            }
        }
    }'''
    variables = {'login': USER_NAME}
    request = simple_request(user_getter.__name__, query, variables)
    return request.json()['data']['user']


def svg_overwrite(filename, age_data, commit_data, star_data, repo_data, follower_data):
    """
    Writes to the SVG file
    """
    svg = open(filename, 'r', encoding='utf-8').read()
    
    # Update the age
    svg = svg.replace('{{age}}', age_data)
    
    # Update stats
    svg = svg.replace('{{commits}}', f'{commit_data:,}')
    svg = svg.replace('{{stars}}', f'{star_data:,}')
    svg = svg.replace('{{repos}}', f'{repo_data:,}')
    svg = svg.replace('{{followers}}', f'{follower_data:,}')
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(svg)


def main():
    """
    Main function to update the README
    """
    print("Starting README update...")
    
    # Calculate age
    birthday = datetime.datetime(2004, 7, 29)
    age = daily_readme(birthday)
    print(f"Age: {age}")
    
    # Get commit count (from account creation to now)
    start_date = '2020-01-01T00:00:00Z'  # Adjust this to your GitHub account creation date
    end_date = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    commits = graph_commits(start_date, end_date)
    print(f"Commits: {commits:,}")
    
    # Get repository count
    repos = graph_repos_stars('repos', ['OWNER'])
    print(f"Repositories: {repos:,}")
    
    # Get stars received
    stars = graph_repos_stars('stars', ['OWNER'])
    print(f"Stars: {stars:,}")
    
    # Get follower count
    user_data = user_getter()
    followers = user_data['followers']['totalCount']
    print(f"Followers: {followers:,}")
    
    # Update both SVG files
    svg_overwrite('dark_mode.svg', age, commits, stars, repos, followers)
    svg_overwrite('light_mode.svg', age, commits, stars, repos, followers)
    
    print("README update complete!")


if __name__ == '__main__':
    main()
