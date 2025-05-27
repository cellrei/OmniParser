<img src="../imgs/header_bar.png" alt="OmniTool Header" width="100%">

# OmniTool (全能工具)

通过 OmniParser 和您选择的视觉模型来控制 Windows 11 虚拟机。

## 产品亮点：

1.  **OmniParser V2** 比 V1 快60%，现已能理解多种操作系统、应用程序及应用内图标！
2.  **OmniBox** 在代理测试方面比其他 Windows 虚拟机少用50%的磁盘空间，同时提供相同的计算机使用API。
3.  **OmniTool** 开箱即用，支持以下视觉模型 - OpenAI (4o/o1/o3-mini)、DeepSeek (R1)、Qwen (2.5VL) 或 Anthropic Computer Use。

## 概览

主要包含三个组件：

<table style="border-collapse: collapse; border: none;">
  <tr>
    <td style="border: none;"><img src="../imgs/omniparsericon.png" width="50"></td>
    <td style="border: none;"><strong>omniparserserver</strong></td>
    <td style="border: none;">运行 OmniParser V2 的 FastAPI 服务器。</td>
  </tr>
  <tr>
    <td style="border: none;"><img src="../imgs/omniboxicon.png" width="50"></td>
    <td style="border: none;"><strong>omnibox</strong></td>
    <td style="border: none;">在 Docker 容器中运行的 Windows 11 虚拟机。</td>
  </tr>
  <tr>
    <td style="border: none;"><img src="../imgs/gradioicon.png" width="50"></td>
    <td style="border: none;"><strong>gradio</strong></td>
    <td style="border: none;">用于提供命令并在 OmniBox 上观察推理和执行过程的用户界面。</td>
  </tr>
</table>

## 注意事项：

1.  尽管 **OmniParser V2** 可以在 CPU 上运行，但如果您希望在 GPU 机器上快速运行，我们已将其分离出来。
2.  **OmniBox** Windows 11 虚拟机 Docker 依赖于 KVM，因此在 Windows 和 Linux 上运行速度较快。它可以在 CPU 机器上运行（不需要 GPU）。**（重要提示：OmniBox 对 KVM 的依赖性意味着它最适合在 Windows 和 Linux 系统上使用，以便获得最佳性能。）**
3.  Gradio 用户界面也可以在 CPU 机器上运行。我们建议在同一台 CPU 机器上运行 **omnibox** 和 **gradio**，并在 GPU 服务器上运行 **omniparserserver**。

## 安装设置

1.  **omniparserserver (OmniParser服务器)**：

    a.  如果您已经为 OmniParser 创建了 conda 环境，则可以直接使用。否则，请按照以下步骤创建：

    b.  请确保已安装 conda（可通过 `conda --version` 命令检查），或从 [Anaconda 网站](https://www.anaconda.com/download/success) 下载安装。

    c.  使用命令 `cd OmniParser` 进入仓库的根目录。 （译者注：请确保您位于克隆的 `OmniParser` 项目的根目录下执行此命令。）

    d.  使用命令 `conda create -n "omni" python==3.12` 创建一个名为 "omni" 的 conda Python 环境，并指定 Python 版本为 3.12。

    e.  使用命令 `conda activate omni` 激活并切换到 "omni" Python 环境。

    f.  使用命令 `pip install -r requirements.txt` 安装所需的依赖包。（译者注：`requirements.txt` 文件位于 `OmniParser` 项目的根目录下。）

    g.  如果您已经配置好了 conda 环境，请从这里继续。

    h.  确保您已在 `weights` 文件夹中下载了 V2 版本的模型权重（**特别注意：caption 权重文件夹必须命名为 `icon_caption_florence`**）。如果尚未下载，请使用以下命令：
        ```bash
        rm -rf weights/icon_detect weights/icon_caption weights/icon_caption_florence 
        for folder in icon_caption icon_detect; do huggingface-cli download microsoft/OmniParser-v2.0 --local-dir weights --repo-type model --include "$folder/*"; done
        mv weights/icon_caption weights/icon_caption_florence
        ```
        （此命令会首先删除 `weights` 目录下可能存在的旧的 `icon_detect`, `icon_caption`, 和 `icon_caption_florence` 文件夹，然后从 Hugging Face Hub 下载 `microsoft/OmniParser-v2.0` 模型的 `icon_caption` 和 `icon_detect` 文件夹到本地的 `weights` 目录，并最后将下载的 `icon_caption` 文件夹重命名为 `icon_caption_florence`。）

    i.  使用命令 `cd OmniParser/omnitool/omniparserserver` 进入服务器应用程序所在的目录。

    j.  使用命令 `python -m omniparserserver` 启动 OmniParser 服务器。

2.  **omnibox (OmniBox虚拟机)**：
    **重要提示：OmniBox 利用 KVM 技术，并且其管理脚本 `./manage_vm.sh` 主要设计用于 Linux 环境或在 Windows 上通过 WSL (Windows Subsystem for Linux) 运行。**

    a.  确保您至少有 30GB 的可用磁盘空间（ISO 文件约5GB，Docker 容器约400MB，虚拟机存储文件夹约20GB）。

    b.  安装 Docker Desktop。您可以从 Docker 官方网站下载并安装。

    c.  访问 [Microsoft 评估中心](https://info.microsoft.com/ww-landing-windows-11-enterprise.html)，接受服务条款，并下载 **Windows 11 企业评估版（90天试用，英文，美国）** ISO 文件（约6GB）。将下载的文件重命名为 `custom.iso`，然后将其复制到 `OmniParser/omnitool/omnibox/vm/win11iso` 目录下。

    d.  使用命令 `cd OmniParser/omnitool/omnibox/scripts` 进入虚拟机管理脚本所在的目录。

    e.  在 Linux 或 WSL 环境下，运行 `./manage_vm.sh create` 命令来构建 Docker 容器（约400MB）并将 ISO 内容安装到存储文件夹（约20GB）。此过程如下图所示，根据您的下载速度，可能需要 20-90 分钟（通常约60分钟）。完成后，终端将显示 `VM + server is up and running!`。您可以通过 NoVNC 查看器 (http://localhost:8006/vnc.html?view_only=1&autoconnect=1&resize=scale) 观察虚拟机桌面上应用程序的安装过程。安装完成后，NoVNC 查看器中显示的终端窗口将不再位于桌面上。如果仍然能看到该终端窗口，请耐心等待，不要进行点击操作！
        ![image](https://github.com/user-attachments/assets/6bd18f81-18e2-4bc5-9170-293a6699481d)

    f.  首次创建后，虚拟机的状态将保存在 `vm/win11storage` 目录中。之后，您可以使用 `./manage_vm.sh start` （启动虚拟机）和 `./manage_vm.sh stop` （停止虚拟机）来管理虚拟机。要删除虚拟机，请使用 `./manage_vm.sh delete` 命令，并手动删除 `OmniParser/omnitool/omnibox/vm/win11storage` 目录。

### macOS 用户特别说明：

针对在 macOS 系统上运行 **omnibox**，请注意以下几点：

1.  **`./manage_vm.sh` 脚本兼容性**：`omnibox` 组件提供的 `./manage_vm.sh` 管理脚本是为 Linux 环境设计的，它依赖于 KVM (Kernel-based Virtual Machine) 技术。因此，此脚本**无法直接在标准的 macOS 安装上运行**。

2.  **分离组件运行**：macOS 用户仍然可以设置和运行 `omniparserserver`（OmniParser 服务器）和 `gradio`（Gradio 客户端界面）这两个组件。这意味着，如果 OmniBox 虚拟机（Windows 11 环境）部署在其他地方（例如，一台单独的 Linux/Windows 物理机，或云虚拟机），macOS 用户可以通过本地的 `gradio` 客户端连接到远程的 `omniparserserver` 和 OmniBox 进行交互。

3.  **在 macOS 上本地运行 Windows 虚拟机**：如果 macOS 用户希望直接在自己的 Mac 电脑上为本项目运行类似 OmniBox 的 Windows 虚拟机（用于开发或本地测试），则需要自行研究和配置支持 KVM 的虚拟化解决方案。例如，可以考虑 Docker Desktop 对 KVM 的实验性支持（如果适用且稳定），或使用其他第三方工具如 UTM（它可以使用 QEMU 后端，QEMU 支持 KVM 指令的模拟和硬件加速）。

4.  **高级设置**：请注意，在 macOS 上配置 KVM 兼容的虚拟化环境属于高级设置，超出了本项目当前脚本和文档的范围。用户需要独立研究相关技术和工具。

5.  **推荐方案**：本项目中 `omnibox` 虚拟机的首选和经过测试的运行环境是 Linux 系统或启用了 WSL (Windows Subsystem for Linux) 的 Windows 系统。

3.  **gradio (Gradio 用户界面)**：

    a.  使用命令 `cd OmniParser/omnitool/gradio` 进入 Gradio 应用所在的目录。

    b.  请确保您已经激活了之前创建的 "omni" conda Python 环境，使用命令 `conda activate omni`。

    c.  使用以下命令启动 Gradio 服务器：
        ```bash
        python app.py --windows_host_url localhost:8006 --omniparser_server_url localhost:8000
        ```
        命令参数说明：
        *   `--windows_host_url localhost:8006`：指定 OmniBox Windows 虚拟机（或您配置的 Windows 主机）VNC 和控制服务器的地址和端口。默认指向本地的 8006 端口。
        *   `--omniparser_server_url localhost:8000`：指定 OmniParser 服务器的地址和端口。默认指向本地的 8000 端口。
        （请根据您实际部署 OmniBox 和 OmniParser 服务器的地址修改这些参数。）

    d.  在浏览器中打开终端输出的 Gradio 应用 URL 地址（通常是类似 `http://127.0.0.1:7888` 或 `http://localhost:7888` 的地址），在Gradio界面中设置您的 API 密钥，然后就可以开始与 AI 代理进行交互了！

## 常见安装错误

### OmniBox 安装时间过长
如果您的网速较慢，并且希望获得一个预装应用较少的最小化虚拟机，可以注释掉此[文件](https://github.com/microsoft/OmniParser/blob/master/omnitool/omnibox/vm/win11setup/setupscripts/setup.ps1)（该文件定义了首次创建容器和虚拟机时安装的所有应用程序）中的第 57 至 350 行。在创建虚拟机以清除任何先前的 omnibox 设置时，请确保遵循下一节中的恢复出厂设置说明。

### 验证错误：Windows 主机无响应 (Validation errors: Windows Host is not responding)
如果您在 Gradio 中点击提交按钮后遇到此错误，这表明虚拟机中运行的、用于接收 Gradio 命令并控制鼠标/键盘的服务器不可用。您可以通过运行 `curl http://localhost:5000/probe` 命令来验证这一点。请确保您的 `omnibox` 已完全完成设置（桌面上不应再有终端窗口）。关于设置所需时间，请参考 omnibox 部分的说明。如果您已完成 omnibox 设置，可能需要稍等片刻。

如果等待 10 分钟后问题仍未解决，请尝试使用脚本命令停止 (`./manage_vm.sh stop`) 和启动 (`./manage_vm.sh start`) 您的 omnibox 虚拟机。

如果这不起作用，请删除您的虚拟机（运行 `./manage_vm.sh delete`，但保留存储文件夹），然后再次运行创建命令。由于使用了现有的存储文件夹，这次创建过程会很快。

最后，如果问题依旧，并且您想将虚拟机完全恢复到出厂设置（即创建一个全新的虚拟机）：
1.  运行 `./manage_vm.sh delete`
2.  删除 `vm/win11storage` 文件夹
3.  运行 `./manage_vm.sh create`

### libpaddle：找不到指定的模块 (libpaddle: The specified module could not be found)
OmniParser 使用的 OCR 库是 PaddlePaddle (飞桨)，在 Windows 系统上，它依赖于 C++ Redistributable (C++ 可再发行组件包)。如果您使用的是 Windows 系统，请确保已安装此组件，然后重新运行 `requirements.txt` 文件来安装依赖。更多详情请参考[此处](https://github.com/microsoft/OmniParser/issues/140#issuecomment-2670619168)。

---

**总结与跨平台兼容性说明**

希望以上安装指南能帮助您顺利配置 OmniTool。

请注意，OmniTool 的核心组件具有不同的跨平台能力：
*   **`omniparserserver` (OmniParser 服务器)** 和 **`gradio` (Gradio 用户界面)**：这两个组件主要依赖于 Python 和 Conda 环境，因此通常可以在 Windows、macOS 和 Linux 系统上成功安装和运行。
*   **`omnibox` (OmniBox 虚拟机)**：此组件用于提供 Windows 11 交互环境。由于其对 KVM 技术的依赖以及当前提供的 `./manage_vm.sh` 管理脚本，其“开箱即用”的完整功能主要针对 **Linux 系统**或**启用了 WSL 的 Windows 系统**。macOS 用户请特别参考[针对 macOS 用户的说明](#macOS-用户特别说明)部分，了解相关限制和替代方案。

为了获得最佳体验和最准确的设置指导，请务必详细阅读您所用操作系统对应的安装设置部分。

---
