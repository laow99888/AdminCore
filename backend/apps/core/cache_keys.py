"""Only these read-through business keys are eligible for administrator cleanup."""


def config_cache_key(identifier, version):
    return f'admincore:config:{identifier}:v{version}'


def dictionary_cache_key(identifier, version):
    return f'admincore:dict:{identifier}:v{version}'
