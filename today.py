import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time
import hashlib
import shutil

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


def graph_commits():
    """
    Uses GitHub's GraphQL v4 API to return total lifetime commit count
    by querying year by year from account creation to now.
    """
    # First get the year the account was created
    query = '''
    query($login: String!) {
        user(login: $login) {
            createdAt
        }
    }'''
    variables = {'login': USER_NAME}
    request = simple_request(graph_commits.__name__, query, variables)

    try:
        created_at = request.json()['data']['user']['createdAt']
        start_year = int(created_at[:4])
    except (KeyError, TypeError, ValueError):
        start_year = 2020  # fallback

    current_year = datetime.datetime.now().year
    total_commits = 0

    # Query each year individually and sum up
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

    for year in range(start_year, current_year + 1):
        start = f"{year}-01-01T00:00:00Z"
        end = f"{year}-12-31T23:59:59Z"
        variables = {'start_date': start, 'end_date': end, 'login': USER_NAME}

        try:
            request = simple_request(graph_commits.__name__, query, variables)
            data = request.json()
            contributions = data['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions']
            total_commits += int(contributions) if contributions else 0
            print(f"  {year}: {contributions} contributions")
        except Exception as e:
            print(f"  {year}: failed ({e})")
            continue

    return total_commits


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
    
    try:
        data = request.json()
        if data and 'data' in data and data['data'] and 'user' in data['data'] and data['data']['user']:
            if count_type == 'repos':
                return data['data']['user']['repositories']['totalCount']
            elif count_type == 'stars':
                edges = data['data']['user']['repositories']['edges']
                return sum([repo['node']['stargazers']['totalCount'] for repo in edges if repo and 'node' in repo])
        return 0
    except (KeyError, TypeError, ValueError) as e:
        print(f"Error getting {count_type}: {e}")
        return 0


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
    
    try:
        data = request.json()
        if data and 'data' in data and data['data'] and 'user' in data['data']:
            return data['data']['user']
        return {'followers': {'totalCount': 0}, 'following': {'totalCount': 0}}
    except (KeyError, TypeError, ValueError) as e:
        print(f"Error getting user data: {e}")
        return {'followers': {'totalCount': 0}, 'following': {'totalCount': 0}}


def svg_overwrite(filename, age_data, commit_data, star_data, repo_data, follower_data):
    """
    Writes to the SVG file, always reading from the .template.svg counterpart
    so that placeholders are never lost between runs.
    """
    # Always read from the template — it permanently holds the {{placeholders}}
    template_filename = filename.replace('.svg', '.template.svg')

    if not os.path.exists(template_filename):
        raise FileNotFoundError(
            f"Template file '{template_filename}' not found. "
            "Please create it by copying your SVG and restoring all "
            "{{age}}, {{commits}}, {{stars}}, {{repos}}, {{followers}} placeholders."
        )

    svg = open(template_filename, 'r', encoding='utf-8').read()

    # Sanity-check that every placeholder is present in the template
    for placeholder in ('{{age}}', '{{commits}}', '{{stars}}', '{{repos}}', '{{followers}}'):
        if placeholder not in svg:
            raise ValueError(
                f"Placeholder '{placeholder}' not found in '{template_filename}'. "
                "Please restore all placeholders in the template file."
            )

    # Substitute live values into a fresh copy of the template
    svg = svg.replace('{{age}}',       age_data)
    svg = svg.replace('{{commits}}',   f'{commit_data:,}')
    svg = svg.replace('{{stars}}',     f'{star_data:,}')
    svg = svg.replace('{{repos}}',     f'{repo_data:,}')
    svg = svg.replace('{{followers}}', f'{follower_data:,}')

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(svg)


def main():
    """
    Main function to update the README
    """
    print("Starting README update...")
    
    try:
        # Calculate age
        birthday = datetime.datetime(2004, 7, 29)
        age = daily_readme(birthday)
        print(f"Age: {age}")

        # Get lifetime commit count
        commits = graph_commits()
        print(f"Total lifetime commits: {commits:,}")
        
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
        
        # Update both SVG files (reads from .template.svg, writes to .svg)
        svg_overwrite('dark_mode.svg',  age, commits, stars, repos, followers)
        svg_overwrite('light_mode.svg', age, commits, stars, repos, followers)
        
        print("README update complete!")
        
    except Exception as e:
        print(f"Error in main: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == '__main__':
    main()
