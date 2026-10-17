/** 只连接 V2 验收脚本创建的临时端口和账户。 */
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
const [workspace, evidence] = process.argv.slice(2);
const require = createRequire(resolve(workspace, "package.json"));
const { chromium, devices, expect: baseExpect } = require("@playwright/test");
const expect = baseExpect.configure({ timeout: 20000 });
const { password } = JSON.parse(
  readFileSync(resolve(evidence, "browser-access.json"), "utf8"),
);
const baseURL = "http://127.0.0.1:18471";
const checks = [],
  browser = await chromium.launch({ headless: true });
let passed = false;
try {
  for (const [name, device] of [
    ["desktop", devices["Desktop Chrome"]],
    ["mobile", devices["iPhone SE"]],
  ]) {
    const context = await browser.newContext({ ...device, baseURL });
    await context.tracing.start({ screenshots: true, snapshots: true });
    const page = await context.newPage(),
      errors = [];
    page.on("pageerror", (error) => errors.push(String(error)));
    try {
      await page.goto("/login");
      await page.getByPlaceholder("用户名", { exact: true }).fill("admin");
      await page.getByPlaceholder("密码", { exact: true }).fill(password);
      await page.getByRole("button", { name: "登录", exact: true }).click();
      await expect(page).toHaveURL(baseURL + "/");
      const token = await page.evaluate(() => localStorage.getItem("token"));
      const headers = { Authorization: "Bearer " + token };
      async function get(path) {
        const response = await context.request.get("/api/v1/" + path, {
          headers,
        });
        expect(response.status()).toBe(200);
        return (await response.json()).data;
      }
      await page.goto("/system/codegen");
      await expect(
        page.getByRole("heading", { name: "代码生成器", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "下载源码", exact: true }),
      ).toBeDisabled();
      await page.getByRole("button", { name: "预览源码", exact: true }).click();
      await expect(page.getByLabel("源码内容", { exact: true })).toContainText(
        "BusinessItem",
      );
      const downloadEvent = page.waitForEvent("download");
      await page.getByRole("button", { name: "下载源码", exact: true }).click();
      const download = await downloadEvent;
      expect(download.suggestedFilename()).toBe("business_items-source.zip");
      await download.saveAs(resolve(evidence, `v2-${name}-source.zip`));
      await page.getByRole("tab", { name: "业务配置", exact: true }).click();
      await page
        .getByLabel("模块标题", { exact: true })
        .fill("修改后需重新预览");
      await expect(
        page.getByRole("button", { name: "下载源码", exact: true }),
      ).toBeDisabled();
      // 导出可保存当前定义，并将表单标记为已保存。
      const definitionDownload = page.waitForEvent("download");
      await page.getByRole("button", { name: "导出定义", exact: true }).click();
      await (
        await definitionDownload
      ).saveAs(resolve(evidence, `v2-${name}-definition.json`));
      await page.screenshot({
        path: resolve(evidence, `v2-${name}-designer.png`),
        fullPage: true,
      });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      checks.push(
        `${name}: generator preview/download, invalidation, definition export, responsive layout`,
      );
      await page.getByRole("button", { name: "导入定义", exact: true }).click();
      const importer = page.getByRole("dialog", {
        name: "导入业务定义",
        exact: true,
      });
      await importer
        .getByLabel("业务定义JSON", { exact: true })
        .fill(
          readFileSync(
            resolve(
              import.meta.dirname,
              "../examples/codegen-v2/purchase-orders.json",
            ),
            "utf8",
          ),
        );
      await importer.getByRole("button", { name: "导入", exact: true }).click();
      await expect(importer).toHaveCount(0);
      await expect(page.getByLabel("模块标识", { exact: true })).toHaveValue(
        "cg_orders",
      );
      await expect(
        page.getByRole("heading", { name: "明细分组", exact: true }),
      ).toBeVisible();
      await page.getByRole("button", { name: "预览源码", exact: true }).click();
      await expect(page.getByLabel("源码内容", { exact: true })).toContainText(
        "PurchaseLine",
      );
      const importedDownload = page.waitForEvent("download");
      await page.getByRole("button", { name: "导出定义", exact: true }).click();
      await (
        await importedDownload
      ).saveAs(resolve(evidence, `v2-${name}-imported.json`));
      checks.push(
        `${name}: import and normalize a real master/detail definition, then preview`,
      );

      await page.goto("/cg-suppliers");
      await expect(
        page.getByRole("heading", { name: "供应商", exact: true }),
      ).toBeVisible();
      await page.getByRole("button", { name: "新增", exact: true }).click();
      let dialog = page.getByRole("dialog", { name: "供应商", exact: true });
      await dialog
        .getByLabel("供应商编码", { exact: true })
        .fill("WEB-" + name);
      await dialog
        .getByLabel("供应商名称", { exact: true })
        .fill("浏览器供应商-" + name);
      await dialog.getByRole("button", { name: "保存", exact: true }).click();
      await expect(dialog).toHaveCount(0);
      await expect(
        page.getByText("浏览器供应商-" + name, { exact: true }),
      ).toBeVisible();
      checks.push(`${name}: generated single-table create`);

      await page.goto("/cg-categories");
      await page.getByRole("button", { name: "新增", exact: true }).click();
      dialog = page.getByRole("dialog", { name: "商品分类", exact: true });
      await dialog.getByLabel("分类编码", { exact: true }).fill("ROOT-" + name);
      await dialog
        .getByLabel("分类名称", { exact: true })
        .fill("父分类-" + name);
      await dialog.getByRole("button", { name: "保存", exact: true }).click();
      await expect(dialog).toHaveCount(0);
      await page
        .getByRole("row")
        .filter({ hasText: "父分类-" + name })
        .getByRole("button", { name: "下级", exact: true })
        .click();
      await page.getByRole("button", { name: "新增", exact: true }).click();
      await dialog
        .getByLabel("分类编码", { exact: true })
        .fill("CHILD-" + name);
      await dialog
        .getByLabel("分类名称", { exact: true })
        .fill("子分类-" + name);
      await dialog.getByRole("button", { name: "保存", exact: true }).click();
      await expect(dialog).toHaveCount(0);
      await expect(
        page.getByText("子分类-" + name, { exact: true }),
      ).toBeVisible();
      await page.getByRole("button", { name: "上一级", exact: true }).click();
      await expect(
        page.getByText("父分类-" + name, { exact: true }),
      ).toBeVisible();
      checks.push(`${name}: generated tree parent/child create and navigation`);

      await page.goto("/cg-orders");
      await page.getByRole("button", { name: "新增", exact: true }).click();
      dialog = page.getByRole("dialog", { name: "采购订单", exact: true });
      await dialog
        .getByLabel("订单编码", { exact: true })
        .fill("PO-WEB-" + name);
      await dialog
        .getByRole("combobox", { name: "供应商", exact: true })
        .click();
      await page
        .getByRole("option", { name: "隔离供应商", exact: true })
        .click();
      await dialog
        .getByRole("combobox", { name: "业务类别", exact: true })
        .click();
      await page.getByRole("option", { name: "办公", exact: true }).click();
      await dialog
        .getByLabel("采购明细 1 商品名称", { exact: true })
        .fill("精确金额商品");
      await dialog
        .getByRole("spinbutton", { name: "采购明细 1 数量", exact: true })
        .fill("2");
      await dialog.getByLabel("采购明细 1 单价", { exact: true }).fill("0.10");
      const lines = dialog.locator("section").filter({
        has: page.getByRole("heading", { name: "采购明细", exact: true }),
      });
      await lines
        .getByRole("button", { name: "添加明细", exact: true })
        .click();
      await dialog
        .getByLabel("采购明细 2 商品名称", { exact: true })
        .fill("第二行商品");
      await dialog
        .getByRole("spinbutton", { name: "采购明细 2 数量", exact: true })
        .fill("3");
      await dialog.getByLabel("采购明细 2 单价", { exact: true }).fill("0.20");
      await expect(dialog.getByLabel("订单金额", { exact: true })).toHaveCount(
        0,
      );
      await page.screenshot({
        path: resolve(evidence, `v2-${name}-aggregate.png`),
        fullPage: true,
      });
      await dialog.getByRole("button", { name: "保存", exact: true }).click();
      await expect(dialog).toHaveCount(0);
      let row = (await get("cg-orders/records/")).items.find(
        (item) => item.code === "PO-WEB-" + name,
      );
      expect(row.amount).toBe("0.80");
      expect(row.display_labels.supplier).toBe("隔离供应商");
      let detail = await get("cg-orders/records/" + row.id + "/");
      expect(detail.lines).toHaveLength(2);
      await page
        .getByRole("row")
        .filter({ hasText: row.code })
        .getByRole("button", { name: "编辑", exact: true })
        .click();
      await expect(
        dialog.getByLabel("采购明细 2 单价", { exact: true }),
      ).toHaveValue("0.20");
      await expect(
        dialog.getByText("隔离供应商", { exact: true }),
      ).toBeVisible();
      await dialog
        .getByLabel("备注", { exact: true })
        .fill("冲突时保留我的草稿");
      const changed = await context.request.patch(
        "/api/v1/cg-orders/records/" + row.id + "/",
        {
          headers,
          data: { version: detail.version, remarks: "另一操作者修改" },
        },
      );
      expect(changed.status()).toBe(200);
      await dialog.getByRole("button", { name: "保存", exact: true }).click();
      const panel = dialog.getByRole("region", {
        name: "编辑冲突",
        exact: true,
      });
      await expect(panel).toBeVisible();
      await expect(dialog.getByLabel("备注", { exact: true })).toHaveValue(
        "冲突时保留我的草稿",
      );
      await expect(
        dialog.getByRole("button", { name: "保存", exact: true }),
      ).toBeDisabled();
      await panel
        .getByRole("button", { name: "查看服务器最新值", exact: true })
        .click();
      await expect(panel).toContainText("另一操作者修改");
      await page.screenshot({
        path: resolve(evidence, `v2-${name}-conflict.png`),
        fullPage: true,
      });
      await panel
        .getByRole("button", {
          name: "载入服务器最新值（替换当前输入）",
          exact: true,
        })
        .click();
      await dialog.getByRole("button", { name: "保存", exact: true }).click();
      await expect(dialog).toHaveCount(0);
      detail = await get("cg-orders/records/" + row.id + "/");
      expect(detail.lines).toHaveLength(2);
      expect(detail.amount).toBe("0.80");
      await page.getByLabel("订单金额 最小值", { exact: true }).fill("1.00");
      await page.getByRole("button", { name: "搜索", exact: true }).click();
      await expect(page.getByText(row.code, { exact: true })).toHaveCount(0);
      await page.getByRole("button", { name: "重置", exact: true }).click();
      await expect(page.getByText(row.code, { exact: true })).toBeVisible();
      await page.getByRole("combobox", { name: "供应商", exact: true }).click();
      await page
        .getByRole("option", { name: "隔离供应商", exact: true })
        .click();
      await page.getByRole("button", { name: "搜索", exact: true }).click();
      await expect(page.getByText(row.code, { exact: true })).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      expect(errors).toEqual([]);
      checks.push(
        `${name}: master/detail money strings, authorized relation/dictionary labels, detail hydration, conflict retention/apply/save, range filter`,
      );
      await context.tracing.stop();
    } catch (error) {
      await page.screenshot({
        path: resolve(evidence, `v2-${name}-failure.png`),
        fullPage: true,
      });
      await context.tracing.stop({
        path: resolve(evidence, `v2-${name}-failure.zip`),
      });
      throw error;
    } finally {
      await context.close();
    }
  }
  passed = true;
} finally {
  writeFileSync(
    resolve(evidence, "browser-report.json"),
    JSON.stringify({ passed, checks }, null, 2),
  );
  await browser.close();
}
