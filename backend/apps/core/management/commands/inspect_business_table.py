import json
from django.core.management.base import BaseCommand, CommandError
from apps.core.codegen.spec import GenerationError
from apps.core.codegen.tables import inspect_table


class Command(BaseCommand):
    help = '只读识别简单业务表并输出生成定义；不读取业务行、不执行DDL'

    def add_arguments(self, parser):
        parser.add_argument('table')
        for name in ['module', 'model', 'title']:
            parser.add_argument('--' + name, required=True)

    def handle(self, *args, **options):
        try:
            result = inspect_table(options['table'], options['module'], options['model'], options['title'])
        except GenerationError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
