from __future__ import annotations

from typing import Final


INTERFACE_THEME_CSS: Final = """
        .q-table__container {
            border-radius: 14px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 10px 28px -18px rgba(15, 23, 42, 0.25);
        }

        .q-table thead th {
            background-color: #f8fafc;
            color: #1f2937;
            font-weight: 500;
        }

        .q-table tbody td {
            border-bottom: 1px solid #e2e8f0;
        }

        .q-table tbody tr:nth-child(even) td {
            background-color: #f9fafb;
        }

        .q-table tbody tr:last-child td {
            border-bottom: none;
        }
        
        .status-output {
            width: 100%;
            max-width: none;
        }
        .status-output pre,
        .status-output code {
            white-space: pre-wrap;
            word-break: break-word;
        }
        .status-output pre {
            margin: 0;
        }
        """

PAGE_CONTAINER_CLASSES = "w-full max-w-screen-2xl mx-auto px-4 md:px-6 space-y-6"
CARD_BASE_CLASSES = "rounded-xl shadow-sm p-4 bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800"
ROW_WRAP_CLASSES = "w-full gap-6 items-stretch flex-wrap"

