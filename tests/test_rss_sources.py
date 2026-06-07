import unittest
from types import SimpleNamespace

from scrapers.rss_opendata import HtmlListScraper, RssOpenDataScraper


class RssSourceTests(unittest.TestCase):
    def test_rss_xml_parse_list_extracts_detail_metadata(self):
        page = SimpleNamespace(body="""
            <rss><channel>
              <item>
                <title>中壢免費音樂會</title>
                <link>https://culture.tycg.gov.tw/News_Content.aspx?n=11099&amp;s=1</link>
                <guid>culture-1</guid>
                <pubDate>Sat, 30 May 2026 00:00:00 GMT</pubDate>
                <description>活動日期：2026年6月1日 活動地點：中壢藝術館</description>
              </item>
            </channel></rss>
        """)
        scraper = RssOpenDataScraper(
            key="culture_rss",
            name="文化局 RSS",
            start_url="https://culture.tycg.gov.tw/OpenData.aspx?SN=test",
        )

        urls = scraper.parse_list(page)

        self.assertEqual(urls, ["https://culture.tycg.gov.tw/News_Content.aspx?n=11099&s=1"])
        item = scraper.feed_items_by_url[urls[0]]
        self.assertEqual(item["title"], "中壢免費音樂會")
        self.assertEqual(item["guid"], "culture-1")
        self.assertIn("活動日期", item["description"])

    def test_rss_item_without_link_is_skipped(self):
        page = SimpleNamespace(body="""
            <rss><channel>
              <item>
                <title>沒有連結的活動</title>
                <guid>not-a-url</guid>
              </item>
            </channel></rss>
        """)
        scraper = RssOpenDataScraper(
            key="broken_rss",
            name="Broken RSS",
            start_url="https://example.tycg.gov.tw/OpenData.aspx?SN=test",
        )

        urls = scraper.parse_list(page)

        self.assertEqual(urls, [])
        self.assertEqual(scraper.parse_warnings[0]["warning"], "rss_no_detail_url")

    def test_json_opendata_parse_list_extracts_detail_url(self):
        page = SimpleNamespace(body="""
            [
              {
                "標題": "客家活動",
                "連結": "https://www.hakka.tycg.gov.tw/News_Content.aspx?n=1&s=2",
                "發布日期": "2026-05-30",
                "內容": "活動時間：2026年6月2日"
              }
            ]
        """)
        scraper = RssOpenDataScraper(
            key="hakka_json",
            name="客家 JSON",
            start_url="https://www.hakka.tycg.gov.tw/OpenData.aspx?SN=test",
        )

        urls = scraper.parse_list(page)

        self.assertEqual(urls, ["https://www.hakka.tycg.gov.tw/News_Content.aspx?n=1&s=2"])
        self.assertEqual(scraper.feed_items_by_url[urls[0]]["title"], "客家活動")

    def test_rss_detail_uses_aspx_parser_and_keeps_rss_metadata(self):
        list_page = SimpleNamespace(body="""
            <rss><channel>
              <item>
                <title>活動 RSS 標題</title>
                <link>https://culture.tycg.gov.tw/News_Content.aspx?n=11099&amp;s=1</link>
                <guid>culture-1</guid>
                <pubDate>2026-05-30</pubDate>
                <description>RSS 摘要</description>
              </item>
            </channel></rss>
        """)
        detail_page = SimpleNamespace(body="""
            <html><body>
              <main>
                <h1>正式活動標題</h1>
                活動日期：2026年6月1日
                活動地點：中壢藝術館
                費用：免費
              </main>
            </body></html>
        """)
        scraper = RssOpenDataScraper(
            key="culture_rss",
            name="文化局 RSS",
            start_url="https://culture.tycg.gov.tw/OpenData.aspx?SN=test",
        )
        url = scraper.parse_list(list_page)[0]

        event = scraper.parse_detail(detail_page, url)

        self.assertEqual(event["title"], "正式活動標題")
        self.assertEqual(event["rss_url"], scraper.start_url)
        self.assertEqual(event["rss_published_at"], "2026-05-30")
        self.assertEqual(event["source_key"], "culture_rss")
        self.assertTrue(event["source_item_id"])

    def test_html_list_scraper_extracts_same_domain_detail_links(self):
        page = SimpleNamespace(body="""
            <html><body>
              <a href="/ch/events/current-events">列表頁</a>
              <a href="/ch/events/current-events/154">活動詳情</a>
              <a href="/ch/open-call/Taoyuan-Fine-Arts-Exhibition">徵件</a>
              <a href="https://other.example.com/ch/events/event-detail/abc">外站</a>
              <a href="javascript:void(0)">JS</a>
            </body></html>
        """)
        scraper = HtmlListScraper(
            key="tmofa_events",
            name="美術館活動",
            start_url="https://tmofa.tycg.gov.tw/ch/events/current-events",
        )

        urls = scraper.parse_list(page)

        self.assertEqual(urls, ["https://tmofa.tycg.gov.tw/ch/events/current-events/154"])

    def test_tmofa_events_allows_event_culture_detail_links(self):
        page = SimpleNamespace(body="""
            <html><body>
              <a href="https://event.culture.tw/mocweb/reg/TMOFA/Detail.init.ctr?actId=60027">
                「暑假？就是玩藝！」2026桃園市兒童美術館夏令營 2026/07/14 - 2026/07/31 地點詳如內頁
              </a>
            </body></html>
        """)
        scraper = HtmlListScraper(
            key="tmofa_events",
            name="美術館活動",
            start_url="https://tmofa.tycg.gov.tw/ch/events/current-events",
        )

        urls = scraper.parse_list(page)

        self.assertEqual(
            urls,
            ["https://event.culture.tw/mocweb/reg/TMOFA/Detail.init.ctr?actId=60027"],
        )
        self.assertEqual(scraper.link_items_by_url[urls[0]]["title"], "「暑假？就是玩藝！」2026桃園市兒童美術館夏令營")


if __name__ == "__main__":
    unittest.main()
