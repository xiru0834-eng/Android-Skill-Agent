# 构建与体验

## 准备

- JDK17：`java -version`、`javac -version`。
- Android SDK：platforms/android-34与build-tools/34.0.0。
- Windows PowerShell在仓库根目录使用`scripts/build-android.ps1`。另提供Gradle8.7/AGP8.5.2项目描述；未提交Gradle二进制wrapper，Gradle链路本次尚未实测。
- 手机Android11以上，或自己创建的Android实验模拟器。

## 构建，不接管设备

在仓库根目录：

```powershell
./scripts/build-android.ps1 -SdkPath 'D:/Android/Sdk'
```

可使用自己的本地debug.keystore，脚本不会上传它。缺失时仅在当前用户的`.android`目录创建开发debug密钥。不要用这个debug签名发布生产应用。

Gradle方式：

```bash
gradle -p android/agent assembleDebug
gradle -p android/parameter-room assembleDebug
```

SDK路径放在两个项目各自的`local.properties`中，或设置Android SDK环境变量；`local.properties`不要提交Git。Gradle只在生成目录适配旧Manifest的package属性，不重写冻结源码；此链路需单独验证，提交副本以离线SDK构建的实际结果为准。

## 免费离线检查

```powershell
python scripts/check-source.py
./android/agent/test-core.ps1
./scripts/test-service-audit.ps1
```

## 体验边界

安装与Accessibility授权必须由设备拥有者在自己的设备上处理。优先使用新的、可重置的实验设备；安装前检查签名和已有数据，不能直接卸载旧研究App来解决签名不一致。

Demo Probe具备多个历史及实验入口。当前host学习／模型链路依赖研究环境配置，公开版没有API密钥、配对码、本机技能批准或用户知识库，**不能导入以后免审核，也不是登录一个GPT账号即可控制任意App**。

阅读`host/`与`model-gateway/`中的历史脚本时，不要直接在真实手机上运行；其中有部署、复位、取消与恢复实验工具。先检查目标、初态、权限、版本、数据备份及调用预算。Git提交任务本身没有调用这些脚本或操作设备。

公开源码中的模型标识沿用研究配置，并不保证每个API账户都有该模型权限。配置可用模型属于后续明确验证，不自动替换或扩大费用。
