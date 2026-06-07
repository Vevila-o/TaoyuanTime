from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase

from events.models import Activity
from events.search_profiles import raw_html_text_for_activity


class RawHtmlTextTests(TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def write_html(self, html):
        path = Path(self.tmpdir.name) / 'activity.html'
        path.write_text(html, encoding='utf-8')
        return str(path)

    def test_prefers_page_content_and_removes_common_navigation_noise(self):
        activity = Activity.objects.create(
            title='農遊趣',
            raw_html_path=self.write_html(
                '''
                <html>
                  <body>
                    <header>網站導覽 全站搜尋</header>
                    <nav>首頁 訊息公告 熱門活動</nav>
                    <main>
                      ::: 首頁 網頁功能 列印內容
                      <div class="page-content">
                        2026花現台七-繡球金針農遊趣
                        活動日期(起)：115-05-09
                        活動地址：百吉休閒農業區遊客中心
                        發布單位：休閒農業科
                        報名網址：https://example.com/register
                        相關檔案 活動簡章 pdf
                      </div>
                    </main>
                    <footer>回上一頁 回最上面 桃園市政府頁尾</footer>
                    <script>var leaked = "不要出現";</script>
                    <style>.hidden { color: red; }</style>
                  </body>
                </html>
                '''
            ),
        )

        text = raw_html_text_for_activity(activity, limit=3000)

        self.assertIn('2026花現台七-繡球金針農遊趣', text)
        self.assertIn('活動日期(起)：115-05-09', text)
        self.assertIn('活動地址：百吉休閒農業區遊客中心', text)
        self.assertIn('發布單位：休閒農業科', text)
        self.assertIn('報名網址：https://example.com/register', text)
        self.assertIn('相關檔案 活動簡章 pdf', text)
        self.assertNotIn('網站導覽', text)
        self.assertNotIn('首頁', text)
        self.assertNotIn('網頁功能', text)
        self.assertNotIn('列印內容', text)
        self.assertNotIn('回上一頁', text)
        self.assertNotIn('桃園市政府頁尾', text)
        self.assertNotIn('不要出現', text)
        self.assertNotIn('hidden', text)

    def test_falls_back_to_body_when_no_main_selector_exists(self):
        activity = Activity.objects.create(
            title='Fallback 活動',
            raw_html_path=self.write_html(
                '''
                <html>
                  <body>
                    <nav>首頁 網站導覽</nav>
                    <section>
                      手作體驗活動
                      活動日期：115-06-01
                      活動地址：桃園市大溪區
                    </section>
                    <footer>回最上面</footer>
                  </body>
                </html>
                '''
            ),
        )

        text = raw_html_text_for_activity(activity, limit=3000)

        self.assertIn('手作體驗活動', text)
        self.assertIn('活動日期：115-06-01', text)
        self.assertIn('活動地址：桃園市大溪區', text)
        self.assertNotIn('網站導覽', text)
        self.assertNotIn('回最上面', text)
