# 获取 Microsoft Edge 版本信息与驱动下载链接

本模块包含两个Python方法：`get_edge_version()` 和 `get_driver_url()`。这两个方法用于获取安装在 Windows 系统上的 Microsoft Edge 浏览器的版本信息，并生成一个适用于该版本的 Edge WebDriver 下载链接。

## 方法介绍

### `get_edge_version()`
此方法用于获取当前安装的 Microsoft Edge 浏览器的版本信息。它通过读取 `msedge.exe` 文件的版本信息，提取主版本号、次版本号、构建号和修订号，最终返回一个完整的版本号字符串。

#### 代码：
```python
import win32api

def get_edge_version():
    try:
        # 获取Edge的版本信息
        path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
        version_info = win32api.GetFileVersionInfo(path, '\\')

        # 获取文件的主要版本和次要版本
        file_version_ms = version_info['FileVersionMS']
        file_version_ls = version_info['FileVersionLS']

        # 将两个部分合并为一个完整的版本号
        major_version = file_version_ms >> 16
        minor_version = file_version_ms & 0xFFFF
        build_version = file_version_ls >> 16
        revision_version = file_version_ls & 0xFFFF

        # 格式化为版本号
        version_num = f"{major_version}.{minor_version}.{build_version}.{revision_version}"
        return version_num
    except Exception as e:
        return f"Error: {str(e)}"

```
### `get_diver_url(edge_version:str)`
此方法用于拼接版本字符串与微软官方的下载链接，最终返回一个完整的Edgedriver下载链接。

#### 代码：
```python
def get_diver_url(edge_version:str):
    return f"https://msedgedriver.azureedge.net/{edge_version}/edgedriver_win64.zip"
```