from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import ElementNotInteractableException
from selenium.webdriver.support import expected_conditions as EC
from loguru import logger
from tqdm import tqdm
from time import sleep
from sys import exit


def get_web_driver(_mute:bool=True, _show_window:bool=True, _wait_time:int=10) -> WebDriver:
    options = webdriver.ChromeOptions()
    if _mute:
        options.add_argument("--mute-audio")
    #service = Service('./chromedriver.exe')
    _driver = webdriver.Chrome(options)

    # 伪无头模式
    if not _show_window:
        _driver.set_window_position(-2000, -2000)

    # 超时等待时间
    _driver.implicitly_wait(_wait_time)

    return _driver

def login(_driver:WebDriver, _username:str, _password:str) -> None:
    # 跳转到综合平台
    logger.info("正在加载登陆界面...")
    _driver.get("https://moodle.scnu.edu.cn/login/index.php")
    _driver.find_element(By.ID, "ssobtn").click()

    # 登录到砺儒云
    logger.info("正在登陆...")
    _driver.find_element(By.ID, "account").send_keys(_username)
    _driver.find_element(By.ID, "password").send_keys(_password)
    _driver.find_element(By.ID, "btn-password-login").click()
    _driver.find_element(By.LINK_TEXT, "确定登录").click()

    # 确定是否成功登录
    try:
        h1_element = _driver.find_element(By.CSS_SELECTOR, 'h1.h2.mb-3.mt-3')
        logger.info("登陆成功!", h1_element.text)
    except NoSuchElementException:
        logger.critical("登陆失败!请检查页面和账号密码")
        sleep(10)
        exit(1)


def play_course_videos(_driver:WebDriver, _course_id:int, _video_urls:list[str], _finish_percentage:int=100) -> None:
    # 进入课程页面
    _driver.get(f"https://moodle.scnu.edu.cn/course/view.php?id={_course_id}")
    _driver.implicitly_wait(10)
    index = 0

    # 遍历播放视频
    for _video in _video_urls:
        index += 1
        logger.info(f"视频[{index}/{len(_video_urls)}]正在播放")
        try:
            _driver.get(_video)
        except Exception as e:
            logger.error("当前视频页面加载出现问题:", e)
            continue

        # 切换到第一个 iframe
        first_iframe = WebDriverWait(_driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
        _driver.switch_to.frame(first_iframe)

        # 切换到第二个 iframe
        second_iframe = WebDriverWait(_driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
        _driver.switch_to.frame(second_iframe)

        # 点击播放按钮
        try:
            _driver.find_element(By.CLASS_NAME, "h5p-control.h5p-pause.h5p-play").click()
        except NoSuchElementException and ElementNotInteractableException:
            logger.error("页面元素处理出错:", _video)
            continue

        # 切换到主界面
        _driver.switch_to.default_content()

        # 检查播放进度
        percentage_value = 0.00
        with tqdm(total=100, desc=f"[{index}/{len(_video_urls)}]视频播放进度", ncols=100, unit="%") as pbar:
            while True:
                # 获取进度百分比
                cell_c3 = float(_driver.find_element(By.CLASS_NAME, "cell.c3").text.strip('%'))
                if cell_c3 != percentage_value:
                    # 更新进度条
                    percentage_value = cell_c3
                    pbar.n = percentage_value
                    pbar.last_print_n = percentage_value
                    pbar.update(0)

                # 如果进度超过既定完成进度，则退出
                if percentage_value > _finish_percentage:
                    sleep(1)
                    pbar.n = 100.00
                    pbar.last_print_n = 100.00
                    pbar.update(0)
                    logger.info(f"视频[{index}/{len(_video_urls)}]播放完成")
                    break
                else:
                    sleep(1)

    # 结束播放
    logger.info("该课程已全部播放完毕")


def get_course_videos(_driver, _course_id) -> list[str]:
    # 访问课程页面
    logger.info("正在进入课程页面...")
    _driver.get(f"https://moodle.scnu.edu.cn/course/view.php?id={_course_id}")

    # 展开课程列表
    try:
        logger.info("正在检测页面状态...")
        _driver.implicitly_wait(2)
        btn_open = _driver.find_element(By.CLASS_NAME, "drawer-toggler.drawer-left-toggle.open-nav.d-print-none")
        btn_open.click()
        logger.info("正在展开课程列表...")
        sleep(2)
    except ElementNotInteractableException:
        pass

    # 爬取视频链接
    _driver.implicitly_wait(10)
    logger.info("正在爬取视频链接...")
    links = _driver.find_elements(By.TAG_NAME, "a")
    video_urls = []
    for link in links:
        video_url = link.get_attribute("href")
        if video_url and "https://moodle.scnu.edu.cn/mod/h5pactivity/view.php" in video_url:
            video_urls.append(video_url)

    # 链接去重显示
    video_urls = list(set(video_urls))
    for video_url in video_urls:
        print(video_url)
    logger.info(f"共计找到{len(video_urls)}个视频")
    return video_urls


if __name__ == "__main__":
    # 用户信息及课程ID
    username = ""
    password = ""

    # 目前只支持四史
    course_id = 16574

    try:
        # 配置日志
        logger.add("./log/run.log", rotation="1 MB", compression="zip")
        logger.info("启动程序")

        # 实例化浏览器
        driver = get_web_driver()

        # 登录到砺儒云平台
        login(driver, username, password)

        # 爬取视频链接列表
        videos = get_course_videos(driver, course_id)

        # 逐个播放网课视频
        play_course_videos(driver, course_id, videos, 90)

        logger.info("退出程序")

    except Exception as ex:
        logger.exception("发生了一个意料之外的错误:", ex)