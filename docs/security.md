# Security

Brevia doesn't provide a specific authentication and authorization mechanism, it has been designed to be as simple as possibile and one of the main goals is to allow integration with existing systems such as CMS, document systems and other content or business applications.

Security can be a very complex topic actually.

## OAuth2 Tokens

Out of the box Brevia provides a very simple mechanism to protect endpoints based on OAuth2 and JWT tokens.

### Activation

To activate token protection of Brevia endpoints you have to define a secret in `TOKENS_SECRET` environment variable (see [Configuration](config.md) section on more details on environment variables and configuration).
This secret will be used to generate and check valid tokens.

Additionally you can define in `TOKENS_USERS` an optional comma separated list of valid user names that must be present in a token. Below more details on how this works.

### Token creation

To create a new token there is a command to launch after activating the virtualenv (using `poetry env activate` for instance)

```bash
create_token -u {username} -d {duration}
```

A [JWT token](https://jwt.io) is created and displayed in the terminal with these options

* with `-u` you can create a token having a specific username as content
* with `-d` you can define a custom duration, default duration is 60 minutes

### Token check

Upon activation via `TOKENS_SECRET` env variable every endpoint is accessible via [Bearer Authentication](https://swagger.io/docs/specification/authentication/bearer-authentication/). Every API call must have an Authorization header in this form

```http
Authorization: Bearer <token>
```

where `<token>` validity is checked using `TOKENS_SECRET` and a matching username is searched in `TOKENS_USERS` if defined

### Status endpoint

There is an exception in tokens check for the [`/status` endpoint](endpoints_overview.md#get-status).
This endpoint can be used by third party services to monitor your API status.
If token check has been validated you may use a special token defined in `STATUS_TOKEN` env var to enable this and only this endpoint to be called without using an actual JWT token.

This particular token must be used via query string like this:

```HTTP
GET /status?token={status-token}
```


## Other Solutions

If this scheme does not suit you or if you want a stronger level of security you could build other solutions using [what FastAPI provides](https://fastapi.tiangolo.com/tutorial/security) or use some third party security tools, like the [ones listed here](https://owasp.org/www-community/api_security_tools). There are really many possible options.
