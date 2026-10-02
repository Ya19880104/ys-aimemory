#!/usr/bin/env python3
"""Read interpolated Compose config JSON from stdin, without echoing credentials."""
import ipaddress
import json
import sys
from urllib.parse import unquote, urlsplit


class ConfigurationError(Exception):
    pass


def validate(config):
    services = config['services']
    env = services['app']['environment']
    db = services['db']['environment']
    url = urlsplit(env['HUB_DATABASE_URL'])
    if (url.scheme != 'postgresql+psycopg' or url.hostname != 'db'
            or url.path != '/memory_hub' or url.username != 'memory_hub'
            or url.port not in (None, 5432)):
        raise ConfigurationError('Use the supplied PostgreSQL service and postgresql+psycopg DSN')
    if unquote(url.password or '') != db['HUB_DB_PASSWORD']:
        raise ConfigurationError('Database URL password does not match HUB_DB_PASSWORD')
    for name in ('POSTGRES_PASSWORD', 'HUB_DB_PASSWORD'):
        password = db[name]
        if len(password) < 24 or any(x in password.lower() for x in ('replace', 'changeme', 'placeholder')):
            raise ConfigurationError('Supply strong operator-provided database passwords of at least 24 characters')
    if db['POSTGRES_PASSWORD'] == db['HUB_DB_PASSWORD']:
        raise ConfigurationError('Use different administrator and application database passwords')
    tokens = json.loads(env['HUB_AUTH_TOKENS'])
    if not isinstance(tokens, dict) or not tokens:
        raise ConfigurationError('HUB_AUTH_TOKENS must be a nonempty JSON object')
    identities = set()
    for token, spec in tokens.items():
        if len(token) < 24 or any(x in token.lower() for x in ('replace', 'changeme', 'placeholder', 'operator_token')):
            raise ConfigurationError('Every token must be a distinct operator-provided random value of at least 24 characters')
        if not isinstance(spec, dict) or spec.get('role') not in ('worker', 'approver', 'admin'):
            raise ConfigurationError('Each token needs a supported role')
        worker = spec.get('worker_id')
        if not isinstance(worker, str) or not worker.strip() or worker in identities:
            raise ConfigurationError('Configure distinct nonempty worker_id values')
        identities.add(worker)
        projects = spec.get('projects')
        if not isinstance(projects, list) or not projects or any(not isinstance(p, str) or not p.strip() or p == '*' for p in projects):
            raise ConfigurationError('Every identity needs an explicit nonempty project allowlist')
    hosts = env.get('HUB_ALLOWED_HOSTS', '').split(',')
    if not hosts or any(not h.strip() or '*' in h for h in hosts):
        raise ConfigurationError('Use an explicit HUB_ALLOWED_HOSTS allowlist without wildcards')
    if env.get('HUB_ALLOW_SQLITE', '').lower() != 'false':
        raise ConfigurationError('SQLite must be disabled for deployment')
    web = [env.get(key, '') for key in ('HUB_WEB_USERNAME', 'HUB_WEB_PASSWORD_HASH', 'HUB_WEB_PROJECTS')]
    if any(web):
        if not all(web):
            raise ConfigurationError('Dashboard requires username, password hash, and project allowlist together')
        import base64
        try:
            algo, n, r, cost, salt, digest = web[1].split('$')
            valid = ((algo, n, r, cost) == ('scrypt', '32768', '8', '1')
                     and len(base64.b64decode(salt, altchars=b'-_', validate=True)) == 16
                     and len(base64.b64decode(digest, altchars=b'-_', validate=True)) == 64)
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise ConfigurationError('Dashboard needs a valid operator-supplied scrypt password hash')
        if any(not part.strip() or part.strip() == '*' for part in web[2].split(',')):
            raise ConfigurationError('Dashboard needs explicit readable project IDs')
        if env.get('HUB_WEB_COOKIE_SECURE', '').lower() != 'true':
            raise ConfigurationError('Deployment dashboard requires Secure cookies and HTTPS')
        if env.get('HUB_WEB_ROLE', 'read_only') not in ('read_only', 'admin'):
            raise ConfigurationError('HUB_WEB_ROLE must be read_only or admin')
        ttl = int(env.get('HUB_WEB_SESSION_TTL', '3600'))
        if not 300 <= ttl <= 28800:
            raise ConfigurationError('Dashboard session TTL must be between 300 and 28800 seconds')
    if services['db'].get('ports'):
        raise ConfigurationError('Do not publish the PostgreSQL port')
    for port in services['app'].get('ports', []):
        if port.get('host_ip') != '127.0.0.1':
            raise ConfigurationError('Plain HTTP must bind only to localhost')
    for port in services.get('nginx', {}).get('ports', []):
        address = ipaddress.ip_address(port.get('host_ip', '0.0.0.0'))
        allowed = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8')
        if address.version != 4 or not any(address in ipaddress.ip_network(n) for n in allowed):
            raise ConfigurationError('HTTPS must bind to an explicit IPv4 loopback or private LAN address')


if __name__ == '__main__':
    try:
        # Compose config escapes every dollar for reuse as Compose input.
        # Reverse that serialization layer once; validate() keeps runtime values.
        validate(json.loads(sys.stdin.read().replace('$$', '$')))
    except Exception as exc:
        # Unexpected exceptions can contain secret input; show only safe validation text.
        message = str(exc) if isinstance(exc, ConfigurationError) else 'Invalid resolved Compose configuration'
        print('Preflight failed: ' + message, file=sys.stderr)
        sys.exit(1)
