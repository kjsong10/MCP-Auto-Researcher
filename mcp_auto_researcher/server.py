from __future__ import annotations

import argparse
import asyncio
import base64
import time
from typing import Any, Dict, List

from fastmcp import FastMCP

from .agent import plan_research, execute_research, build_report, memory


server = FastMCP()


@server.tool
async def ping(message: str = "pong") -> Dict[str, Any]:
    return {"ok": True, "message": message}


@server.tool
async def plan_research_tool(research_question: str) -> Dict[str, Any]:
    return await plan_research(research_question)


@server.tool
async def execute_research_tool(workflow_id: str, research_question: str) -> Dict[str, Any]:
    return await execute_research(workflow_id, research_question)


@server.tool
async def build_report_tool(workflow_id: str, format: str = "markdown") -> Dict[str, Any]:
    return build_report(workflow_id, format=format)


@server.tool
async def autonomous_research_assistant(
    research_question: str,
    output_format: str = "markdown",
) -> Dict[str, Any]:
    workflow_id = f"auto_{int(time.time())}"
    await plan_research(research_question)
    await execute_research(workflow_id, research_question)
    report = build_report(workflow_id, format=output_format)
    # Flatten report fields to top-level for client compatibility
    flattened: Dict[str, Any] = {"workflow_id": workflow_id, **report}
    return flattened


# -------------------------- Resources -----------------------------------------

@server.resource(
    "resource://report/{workflow_id}",
    title="Research Report (Markdown)",
    description="Rendered research report for a workflow in Markdown",
    mime_type="text/markdown",
)
def report_markdown_resource(workflow_id: str) -> str:
    result = build_report(workflow_id, format="markdown")
    return result.get("content", "")


@server.resource(
    "resource://report/{workflow_id}/pdf",
    title="Research Report (PDF)",
    description="Rendered research report for a workflow in PDF",
    mime_type="application/pdf",
)
def report_pdf_resource(workflow_id: str) -> bytes:
    result = build_report(workflow_id, format="pdf")
    b64 = result.get("content_b64", "")
    return base64.b64decode(b64) if b64 else b""


@server.resource(
    "resource://workflow/{workflow_id}.json",
    title="Workflow JSON",
    description="Raw workflow data and artifacts as JSON",
    mime_type="application/json",
)
def workflow_json_resource(workflow_id: str) -> Dict[str, Any]:
    return memory.get(workflow_id)


@server.resource(
    "resource://report/{workflow_id}/chart.png",
    title="Report Chart (PNG)",
    description="Chart image produced during research execution",
    mime_type="image/png",
)
def report_chart_png_resource(workflow_id: str) -> bytes:
    wf = memory.get(workflow_id)
    chart_b64 = wf.get("artifacts", {}).get("chart")
    return base64.b64decode(chart_b64) if chart_b64 else b""


@server.resource(
    "resource://about",
    title="About Auto Researcher",
    description="Basic information about this MCP server",
    mime_type="text/markdown",
)
def about_resource() -> str:
    return (
        "# MCP Auto Researcher\n\n"
        "This server exposes tools, resources, and prompts for autonomous research.\n\n"
        "- Tools: plan, execute, build, autonomous\n"
        "- Resources: report (md/pdf), workflow JSON, chart PNG\n"
        "- Prompts: research_summary, improve_citations, use_report_by_workflow\n"
    )


# ---------------------------- Prompts -----------------------------------------

@server.prompt("research_summary")
def research_summary_prompt(question: str) -> List[Dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a research assistant. Provide a concise, neutral, and well-structured summary. "
                "Use bullet points and include a brief conclusion."
            ),
        },
        {
            "role": "user",
            "content": f"Research question: {question}",
        },
    ]


@server.prompt("improve_citations")
def improve_citations_prompt(question: str) -> List[Dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": (
                "Ensure every factual claim is backed by a source. Add or refine citations as Markdown links."
            ),
        },
        {
            "role": "user",
            "content": (
                "Review the draft report and ensure sources are present and properly titled. "
                f"Focus on: {question}"
            ),
        },
    ]


@server.prompt("use_report_by_workflow")
def use_report_by_workflow_prompt(workflow_id: str) -> List[Dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": {
                "type": "resource",
                "resource": {
                    "uri": f"resource://report/{workflow_id}",
                    "text": "Server-provided report for reference",
                },
            },
        }
    ]


async def run_stdio() -> None:
    await server.run_stdio_async()


async def run_http(host: str = "127.0.0.1", port: int = 8000) -> None:
    await server.run_http_async(host=host, port=port)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MCP Auto Researcher (FastMCP 2.0)")
    p.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.transport == "stdio":
        asyncio.run(run_stdio())
    else:
        asyncio.run(run_http(args.host, args.port))


if __name__ == "__main__":
    main()

