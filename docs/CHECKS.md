# 提交副本验证记录

验证日期：2026-10-09。验证对象：本仓库公开提交副本。

## 实际运行结果

| 检查 | 实际结果 | 不能替代的证据 |
|---|---|---|
| 公开源码扫描与解析 | 831个文件；554个Python、15个XML/SVG、5个JSON解析通过，8个Markdown文件链接有效；常见密钥／私钥命中0 | 不等于完整安全审计 |
| Android纯逻辑回归 | **71/71测试类运行成功** | 不是71个Android任务，也不是自然语言E2E |
| 服务审计辅助类 | **25/25断言通过**；同时包含在71类中，不重复累计 | 不是Android服务出口或ANR实测 |
| Agent离线构建 | **PASS**；Probe109 / 0.71-service-audit，APK签名核验通过 | 不代表已安装或完成设备资格 |
| Parameter Room离线构建 | **PASS**；Room6 / 0.8-parameter-room，APK签名核验通过 | 不代表跨设备任务通过 |
| 原始文件保持 | 810份选定原始文件SHA-256均未变化 | 不代表所有历史批次已重新测试 |
| Gradle替代构建链路 | **NOT_TESTED**；本次使用SDK离线脚本 | 不能填写Gradle构建PASS |
| 模型／手机／模拟器操作 | **0次** | 本次不是设备或模型验收 |

以上计数是在Git初始化前的提交目录上取得的；最终Git索引再次单独扫描。之后补充本页和交付文档不改变Android实现。

## 复现命令

在仓库根目录使用JDK17、Android SDK34与Build Tools34.0.0：

```powershell
python -B scripts/check-source.py
./android/agent/test-core.ps1
./scripts/test-service-audit.ps1
./scripts/build-android.ps1 -SdkPath 'D:/Android/Sdk'
# 已暂存文件还可检查实际Git索引：
python -B scripts/check-source.py --staged
```

构建只读源文件并输出APK，不安装或调用设备；`apksigner verify`在构建脚本中执行。Javac产生旧API弃用提示，没有编译失败。

| APK | SHA-256 |
|---|---|
| Agent | `353835641160a92c88a65cee6ff2616446bbe61ac4136e8123f4a910579a6377` |
| Parameter Room | `e27d5ce47a30c8bef7fae2e358c0f05219260e4cf3da933f161a42d415ba9f9d` |

上述hash是研究机本次实际debug构建的标识；不同机器的签名与打包环境可能产生不同hash，不把同hash作为新机器的通用构建要求。签名私钥与APK不提交Git。

## 提交副本的工程调整

- 复制声明范围内的源码与合同，原目录不动。
- 为两个App补充Gradle项目描述和可指定SDK路径的离线构建脚本。
- 公开副本的纯逻辑测试清单增加已有`PortableServiceAudit`辅助类，使随附测试可编译；未修改Android业务源码、权限、参数、安全守卫或八秒约束。
- 服务审计测试保留原有打印标签`NOT_ANDROID_NOT_APPLIED`，那是原提案测试的历史输出；本仓库确实包含已应用的109源码。该标签不能当作设备执行证据。

**公开提交验证通过，不改变当前W1的BLOCKED_NATIVE_QUALIFICATION状态。** 历史项目实验与当前副本构建分别记录，详见[实际进度](STATUS.md)。
