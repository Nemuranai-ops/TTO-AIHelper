# Resources

A plain list of links. Each line is one resource; the type is inferred from the
URL or path pattern, so you never label anything yourself.

Put each link on its own line, as a bullet, a bare URL, or wrapped in angle
brackets - any of the three works. Delete every example below (they are all
commented out with a leading #, which this file's parser always skips, the
same way it skips headings) and add your real links in their place.

## Jira

# A full issue URL looks like this:
# https://your-org.atlassian.net/browse/PAY-12
#
# Or just the bare key, with nothing else on the line:
# PAY-13
#
# A saved JQL search - anything with jql=... in the URL, or a bare
# project=/issuetype=/labels= filter:
# https://your-org.atlassian.net/issues/?jql=project=PAY AND labels="checkout"

## Confluence

# A specific page:
# https://your-org.atlassian.net/wiki/spaces/PAY/pages/123456789/Checkout-Rules
#
# Or a whole space - every page in it gets ingested:
# https://your-org.atlassian.net/wiki/spaces/PAY

## Bitbucket

# https://bitbucket.org/your-org/checkout-service

## OpenAPI / Swagger spec

# Usually you won't add one of these by hand - the system finds specs on its
# own while reading a Bitbucket repository above. Add one here only for a spec
# that lives somewhere else, as a path ending openapi.yaml / openapi.json /
# swagger.yaml / swagger.json and NOT under a bitbucket.org URL (a bitbucket.org
# link is always read as the repository itself, even if the path ends in
# openapi.yaml):
# https://docs.your-org.com/checkout/openapi.yaml

## Local folder

# A path to an existing directory (e.g. Figma screenshot exports) is picked up
# as a design-folder resource, not a link:
# ./designs/checkout
