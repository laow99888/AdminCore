from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CredentialScheme(OpenApiAuthenticationExtension):
    target_class = 'apps.api_credentials.authentication.APICredentialAuthentication'
    name = 'apiCredential'

    def get_security_definition(self, auto_schema):
        return {'type': 'apiKey', 'in': 'header', 'name': 'Authorization',
                'description': 'ApiToken ac_<credential UUID without hyphens>.<one-time secret>; only dedicated read-only gateway routes.'}
