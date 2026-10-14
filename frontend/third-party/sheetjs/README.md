# SheetJS Community Edition

- 包：`xlsx` 0.20.3，未经修改的官方包位于 `vendor/xlsx-0.20.3.tgz`。
- 来源：https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz
- SHA512：`a0b0eade3c3b01c2ea2961f60210a9553665f267fa5f661178ff8d7a1d12254cd5fc1759623b61f78b46e6da22301d4f3eb62dc4e09f6a850292fb6e1fedc024`
- 许可证：Apache-2.0，版权归 SheetJS LLC，完整许可及包附带版权通知见同目录 LICENSE；原包没有单独 NOTICE 文件。
- 安装来源和 npm integrity 固定在 package-lock.json。安装/构建使用仓库原包，不运行在线下载器；浏览器运行时不访问第三方CDN。
- 仅导出：专用临时Worker使用ES模块的utils/write，不读取上传文件或不可信工作簿。
- 构建将本目录复制到 `/third-party/sheetjs/`，随前端镜像分发。

官方安装依据：https://docs.sheetjs.com/docs/getting-started/installation/frameworks/
