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


def get_diver_url(edge_version:str):
    return f"https://msedgedriver.azureedge.net/{edge_version}/edgedriver_win64.zip"
