import unittest
from unittest.mock import Mock

from rich.markdown import Markdown

from ui.cli.output_formatter import SimpleMarkdownFormatter, create_formatter


class TestOutputFormatter(unittest.TestCase):
    def test_simple_formatter_streams_chunks_immediately(self):
        formatter = SimpleMarkdownFormatter(show_stream=True)
        formatter.console = Mock()

        formatter.add_chunk("hello")

        formatter.console.print.assert_called_once_with(
            "hello", end="", markup=False
        )

    def test_simple_formatter_does_not_reprint_full_content_after_streaming(self):
        formatter = SimpleMarkdownFormatter(show_stream=True)
        formatter.console = Mock()

        formatter.add_chunk("hello")
        formatter.render_final()

        self.assertEqual(formatter.console.print.call_count, 2)
        formatter.console.print.assert_any_call("hello", end="", markup=False)
        formatter.console.print.assert_any_call()

    def test_create_formatter_non_live_renders_markdown_on_completion(self):
        formatter = create_formatter(use_live=False)

        self.assertIsInstance(formatter.markdown_formatter, SimpleMarkdownFormatter)
        self.assertFalse(formatter.markdown_formatter.show_stream)

        formatter.markdown_formatter.console = Mock()
        formatter.add_chunk("| Name | Value |\n| --- | --- |\n| AZ | Rich |")
        formatter.render_final()

        formatter.markdown_formatter.console.print.assert_called_once()
        rendered = formatter.markdown_formatter.console.print.call_args.args[0]
        self.assertIsInstance(rendered, Markdown)

    def test_create_formatter_can_keep_plain_streaming_output(self):
        formatter = create_formatter(use_live=False, show_stream=True)

        self.assertTrue(formatter.markdown_formatter.show_stream)

    def test_unified_formatter_prints_dim_tool_detail(self):
        formatter = create_formatter(use_live=False)
        formatter.console = Mock()

        formatter.print_tool_detail("operation='diff' · base_ref='master'")

        formatter.console.print.assert_called_once_with(
            "  ↳ operation='diff' · base_ref='master'",
            style="dim grey50",
            markup=False,
        )


if __name__ == "__main__":
    unittest.main()
