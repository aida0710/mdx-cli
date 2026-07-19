from unittest.mock import MagicMock, patch

from mdx_cli.api.spinner import ProgressStatus, progress_status


def test_progress_status_message_format():
    """メッセージは「ラベル... (done/total)」+ 任意のサフィックス。"""
    p = ProgressStatus("取得中", 10, enabled=False)
    assert p._message() == "取得中... (0/10)"
    p.advance()
    assert p._message() == "取得中... (1/10)"
    p.advance("vm-2")
    assert p._message("vm-2") == "取得中... (2/10) vm-2"


def test_progress_status_disabled_is_noop():
    """enabled=False（--json時）はスピナーを作らず advance も安全。"""
    with patch("mdx_cli.api.spinner.err_console") as mock_console:
        p = ProgressStatus("取得中", 3, enabled=False)
        p.start()
        p.advance("x")
        p.stop()
        mock_console.status.assert_not_called()


def test_progress_status_updates_underlying_status():
    """advance のたびに Status.update が新メッセージで呼ばれる。"""
    with patch("mdx_cli.api.spinner.err_console") as mock_console:
        mock_status = MagicMock()
        mock_console.status.return_value = mock_status
        p = ProgressStatus("停止待機中", 2)
        p.start()
        p.advance("完了: vm-1")
        mock_status.update.assert_called_with("停止待機中... (1/2) 完了: vm-1")
        p.stop()
        mock_status.stop.assert_called_once()


def test_progress_status_context_manager_stops_on_exit():
    """with を抜けると必ず stop される（例外時も）。"""
    with patch("mdx_cli.api.spinner.err_console") as mock_console:
        mock_status = MagicMock()
        mock_console.status.return_value = mock_status
        try:
            with progress_status("取得中", 5) as p:
                p.advance()
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        mock_status.stop.assert_called_once()
