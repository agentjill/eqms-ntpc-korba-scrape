from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
import keyboard
import logging
from pathlib import Path
import time
import threading
import toml
from typing import List, Optional, Self, Union
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Set up logging
logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s.%(msecs)03d] - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

exit_flag = threading.Event()

Max_SIZE = 50*1024


def check_for_exit():
    while not exit_flag.is_set():
        if keyboard.is_pressed('esc'):
            logger.info("Esc pressed")
            exit_flag.set()
        time.sleep(0.1)


def get_time() -> str:
    return (datetime.now(UTC) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def append_to_file(file_path: Path, text: str):
    max_size = Max_SIZE
    line = "------------------------------------"

    # Check if file exists and its size
    if file_path.exists() and file_path.stat().st_size > max_size:
        with open(file_path, 'r+', encoding='utf-8') as file:
            content = file.read()
            # Find the indices of the first two '-------------'
            first_sep = content.find(line)
            second_sep = content.find(
                line, first_sep + len(line))

            # If two separators are found, remove content between them
            if first_sep != -1 and second_sep != -1:
                content = content[:first_sep] + content[second_sep:]
                file.seek(0)
                file.write(content)
                file.truncate()

    # Append the new text at the end of the file
    with open(file_path, 'a', encoding='utf-8') as file:
        file.write(f"{text}\n")


def print_with_log(item, file_path: Path, time_req: bool, level):
    match level:
        case 'info':
            logger.info(item)
        case 'error':
            logger.error(item)
        case _:
            print(item)
    if time_req:
        item = f"[{get_time()}]: {item}"
    append_to_file(file_path=file_path, text=item)


@dataclass(slots=True)
class LoginData():
    email: str
    password: str


@dataclass(slots=True)
class SiteData():
    url: str
    login_form: str
    password_selector: str
    menu_content: str
    dashboard: str
    master_tab_selector: str
    caaqms_cems_title_selector: str
    caaqms_cems_master_selector: str
    eqms_master_selector: str


@dataclass(slots=True)
class OutData():
    data_out: Path
    log_out: Path


@dataclass(slots=True)
class ConfigData():
    login_data: LoginData
    site_data: SiteData
    output: OutData
    loop_time_sec: float
    log_size_kb: int

    @classmethod
    def read(cls, file_path='config.toml') -> Union[Self, Exception]:
        try:
            with open(file_path, "r") as f:
                config = toml.load(f)

            out_data = OutData(
                data_out=Path(config["data_out"]["output"]),
                log_out=Path(config["data_out"]["log"])
            )

            login_data = LoginData(**config["login"])
            site_data = SiteData(**config["site"])
            loop_time_sec = max(
                float(config["application"]["loop_time_sec"]), 30)
            log_size_kb = max(
                int(config["application"]["log_size_kb"]), 50)*1024

            return ConfigData(
                login_data=login_data,
                site_data=site_data,
                output=out_data,
                loop_time_sec=loop_time_sec,
                log_size_kb=log_size_kb
            )

        except Exception as e:
            logger.error(f"Error reading config: {str(e)}")
            raise


class Param:
    __slots__ = ['value_raw', 'value_parsed',
                 'unit', 'is_health_ok', 'update_time']

    def __init__(self, unit: str):
        self.value_raw: Optional[str] = None
        self.value_parsed: Optional[float] = None
        self.unit: str = unit
        self.is_health_ok: bool = False
        self.update_time = get_time()

    def set_float_check_value(self, value: str):
        self.value_raw = value
        self.update_time = get_time()
        try:
            self.value_parsed = next(
                float(x) for x in value.split() if x.replace('.', '').isdigit())
            self.is_health_ok = True
        except StopIteration:
            self.is_health_ok = False

    def __str__(self):
        if self.value_raw is None:
            return "Uninitialized - No Value fetched"
        elif not self.is_health_ok:
            return f'Invalid Data - Raw value: "{self.value_raw}"'
        else:
            return f"{self.value_parsed} {self.unit}"


class Caaqms:
    def __init__(self, name, config: ConfigData, selector_idx: int):
        self.name: str = name
        self.selector: str = config.site_data.caaqms_cems_master_selector.replace(
            "$item", str(selector_idx))
        self.selector_idx = selector_idx
        self.unit = None
        self.params = {
            'co': Param("mg/m³"),
            'co2': Param("ppm"),
            'nox': Param("μg/m³"),
            'pm10': Param("μg/m³"),
            'pm2_5': Param("μg/m³"),
            'so2': Param("μg/m³")
        }

    def __str__(self):
        return f"{self.name} DATA:- " + ", ".join(f"{k.upper()}: {v}" for k, v in self.params.items())

    def fetch_data(self, driver: WebDriver, file_name, config: ConfigData):
        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, config.site_data.master_tab_selector.replace("$tab", "1")))).click()

            if self.unit is None:
                pre = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, config.site_data.caaqms_cems_title_selector.replace("$item", str(self.selector_idx))))).text
                x = str(
                    pre.split('_')[-1]).upper().lstrip() if pre.split('_')[-1].upper().isprintable() else None
                if x is not None:
                    self.unit = x
                    self.name = self.name + self.unit
                    file_name = self.name + ".txt"

            for i, (param_name, param) in enumerate(self.params.items(), 1):
                value = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, self.selector.replace("$param", str(i))))).text
                param.set_float_check_value(value)

            print_with_log(f"{self}", config.output.log_out, True, 'info')

            with open(config.output.data_out / file_name, 'w', encoding='utf-8') as f:
                f.write(str(self))

        except Exception as e:
            print_with_log(f"Error fetching data for {self.name}: {
                           str(e)}", config.output.log_out, True, 'error')


class Cems:
    def __init__(self, name, config: ConfigData, selector_idx: int):
        self.name: str = name
        self.selector: str = config.site_data.caaqms_cems_master_selector.replace(
            "$item", str(selector_idx))
        self.selector_idx = selector_idx
        self.unit = None
        self.params = {
            'nox': Param("mg/nm³"),
            'pm': Param("mg/nm³"),
            'so2': Param("mg/nm³")
        }

    def __str__(self):
        return f"{self.name} DATA:- " + ", ".join(f"{k.upper()}: {v}" for k, v in self.params.items())

    def fetch_data(self, driver: WebDriver, file_name: str, config: ConfigData):
        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, config.site_data.master_tab_selector.replace("$tab", "2")))).click()

            if self.unit is None:
                pre = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, config.site_data.caaqms_cems_title_selector.replace("$item", str(self.selector_idx))))).text
                x = int(
                    pre.split('_')[-1]) if pre.split('_')[-1].isdigit() else None
                if x is not None:
                    self.unit = x
                    self.name = self.name + str(x)
                    file_name = self.name + ".txt"

            for i, (param_name, param) in enumerate(self.params.items(), 1):
                value = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, self.selector.replace("$param", str(i))))).text
                param.set_float_check_value(value)

            print_with_log(f"{self}", config.output.log_out, True, 'info')

            with open(config.output.data_out / file_name, 'w', encoding='utf-8') as f:
                f.write(str(self))
        except Exception as e:
            print_with_log(f"Error fetching data for {self.name}: {
                           str(e)}", config.output.log_out, True, 'error')


class Eqms:
    def __init__(self, name, selector):
        self.name: str = name
        self.selector: str = selector
        self.params = {
            'bod_toc': Param("mg/L"),
            'cod_toc': Param("mg/L"),
            'ph': Param("pH"),
            'toc': Param("mg/L"),
            'tss': Param("mg/L"),
            'temperature': Param("°C")
        }

    def __str__(self):
        return f"{self.name} Data:- " + ", ".join(f"{k.upper()}: {v}" for k, v in self.params.items())

    def fetch_data(self, driver: WebDriver, file_name: str, config: ConfigData):
        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, config.site_data.master_tab_selector.replace("$tab", "3")))).click()

            for i, (param_name, param) in enumerate(self.params.items(), 1):
                value = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, self.selector.replace("$param", str(i))))).text
                param.set_float_check_value(value)

            print_with_log(f"{self}", config.output.log_out, True, 'info')

            with open(config.output.data_out / file_name, 'w', encoding='utf-8') as f:
                f.write(str(self))
        except Exception as e:
            print_with_log(f"Error fetching data for {self.name}: {
                           str(e)}", config.output.log_out, True, 'error')


@contextmanager
def start_browser_and_login(config: ConfigData):
    driver = None
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--incognito")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-gpu-compositing")
    chrome_options.add_argument("--disable-image-loading")
    chrome_options.add_argument("--disable-bundled-plugins")
    chrome_options.add_argument("--disable-flash")
    chrome_options.add_argument("--disable-save-password-bubble")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-media-stream")
    chrome_options.add_argument("--disable-dev-tools")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument(
        "--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--ignore-certificate-errors")
    # INFO = 0, WARNING = 1, LOG_ERROR = 2, LOG_FATAL = 3
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--disable-translate")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-autofill")
    chrome_options.add_argument("--disable-speech-api")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    chrome_options.add_argument("--disable-dev-shm-usage")

    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.popups": 2,
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values.geolocation": 2,
        "profile.default_content_setting_values.media_stream_mic": 2,
        "profile.default_content_setting_values.media_stream_camera": 2,
        "profile.default_content_setting_values.automatic_downloads": 2,
        "profile.default_content_setting_values.ppapi_broker": 2,
        "profile.default_content_setting_values.ssl_cert_decisions": 2,
        "profile.default_content_setting_values.auto_select_certificate": 2,
        "profile.default_content_setting_values.mixed_script": 2,
        "profile.default_content_setting_values.media_stream": 2,
        "profile.default_content_setting_values.protocol_handlers": 2,
        "profile.default_content_setting_values.plugins": 2,
        "profile.default_content_setting_values.midi_sysex": 2,
        "profile.default_content_setting_values.push_messaging": 2,
        "profile.default_content_setting_values.metro_switch_to_desktop": 2,
        "profile.default_content_setting_values.protected_media_identifier": 2,
        "profile.default_content_setting_values.site_engagement": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(config.site_data.url)

        WebDriverWait(driver, 10).until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, config.site_data.login_form))).send_keys(
            config.login_data.email + Keys.RETURN)

        WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, config.site_data.password_selector))).send_keys(
            config.login_data.password + Keys.RETURN)

        yield driver
    except Exception as e:
        print_with_log(f"Error during login: {
                       str(e)}", config.output.log_out, True, 'error')
        raise
    finally:
        if driver is not None:
            driver.close()
            driver.quit()


def main():
    logger.info("Press ESC to exit at any time.\n")
    # Start the exit checker in a separate thread
    exit_thread = threading.Thread(target=check_for_exit)
    exit_thread.daemon = True
    exit_thread.start()

    try:
        config = ConfigData.read()
        logger.info("successfully read config file")

        global Max_SIZE
        Max_SIZE = config.log_size_kb
        config.output.data_out.mkdir(parents=True, exist_ok=True)

        config.output.log_out.mkdir(parents=True, exist_ok=True)

        config.output.log_out = Path(config.output.log_out/"log.txt")

    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        exit()

    caaqms_sites: List[Caaqms] = []
    for i in range(1, 4):
        caaqms_sites.append(
            Caaqms(f"AAQMS ", config, i)
        )

    cems_units: List[Cems] = []
    for i in range(1, 8):
        cems_units.append(
            Cems(f"CEMS UNIT# ", config, i)
        )

    eqms = Eqms("ETP", config.site_data.eqms_master_selector)

    # driver = start_browser_and_login(config)
    with start_browser_and_login(config) as driver:
        logger.info("Driver initialisation succesful")

        WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, config.site_data.menu_content))).click()
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, config.site_data.dashboard))).click()

        if (not config.output.log_out.exists()) or config.output.log_out.stat().st_size == 0:
            print_with_log("------------------------------------",
                           config.output.log_out, False, 'ignore')
        print_with_log("Application Started.",
                       config.output.log_out, True, 'info')
        print_with_log("------------------------------------",
                       config.output.log_out, False, 'ignore')

        while not exit_flag.is_set():
            start_time = time.time()

            try:
                for caaqms in caaqms_sites:
                    caaqms.fetch_data(driver, f"{caaqms.name}.txt", config)

                for cems in cems_units:
                    cems.fetch_data(driver, f"{cems.name}.txt", config)

                eqms.fetch_data(driver, "ETP.txt", config)

                print_with_log("------------------------------------",
                               config.output.log_out, False, 'ignore')

            except Exception as e:
                print_with_log(f"Error occurred: {
                               str(e)}", config.output.log_out, True, 'error')

            # Calculate remaining time to sleep
            elapsed_time = time.time() - start_time
            sleep_time = max(0, config.loop_time_sec - elapsed_time)

            # Sleep in short intervals, checking the running flag
            for _ in range(int(sleep_time / 0.5)):
                time.sleep(0.5)
                if exit_flag.is_set():
                    break

    print_with_log("Received Esc, Preparing to exit...",
                   config.output.log_out, True, 'info')
    print_with_log("------------------------------------",
                   config.output.log_out, False, 'ignore')

    print_with_log(f"Application Ended", config.output.log_out, True, 'info')
    print_with_log("------------------------------------",
                   config.output.log_out, False, 'ignore')


if __name__ == '__main__':
    main()
    logger.info("Exiting Application")
