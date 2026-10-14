"""默认仅预览；应用必须提供此前计划和逐个显式选择的文件。"""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from apps.core.codegen.spec import GenerationError, parse_definition
from apps.core.codegen.render import render
from apps.core.codegen.plans import make_plan, preview_diff, apply_plan
from apps.core.codegen.tables import verify_table


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise GenerationError('定义或计划文件超过1MB')
    return json.loads(path.read_text(encoding='utf-8'))


class Command(BaseCommand):
    help = '从JSON业务定义预览/选择性生成模块；不自动登记、启用或迁移'

    def add_arguments(self, parser):
        parser.add_argument('--definition', required=True)
        parser.add_argument('--output', required=True)
        parser.add_argument('--plan', help='显式保存预览计划，拒绝覆盖已存在文件')
        parser.add_argument('--apply-plan', help='应用之前保存的预览计划')
        parser.add_argument('--select', action='append', default=[], help='选择相对路径；每个文件单独重复此选项')

    def handle(self, *args, **options):
        try:
            if options['plan'] and options['apply_plan']:
                raise GenerationError('预览与应用不能同时执行')
            if options['select'] and not options['apply_plan']:
                raise GenerationError('选择文件需要提供此前计划')
            raw = read_json(options['definition'])
            definition = parse_definition(raw)
            if definition.table:
                verify_table(definition)
            files = render(definition)
            root = Path(options['output'])
            if options['apply_plan']:
                result = apply_plan(root, read_json(options['apply_plan']), raw, files, options['select'])
                self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                plan = make_plan(root, raw, files)
                # 差异可失败（例如旧文件不是文本），保存前完整检验。
                difference = preview_diff(root, files)
                if options['plan']:
                    with Path(options['plan']).open('x', encoding='utf-8') as destination:
                        json.dump(plan, destination, ensure_ascii=False, indent=2)
                self.stdout.write(json.dumps(plan, ensure_ascii=False, indent=2))
                self.stdout.write(difference)
        except (GenerationError, OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CommandError(str(error)) from error
