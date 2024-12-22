import os
import re
from typing import Optional, List

from mkdocs.config.config_options import Type
from mkdocs.plugins import get_plugin_logger, BasePlugin
from prance import ResolvingParser
from pydantic import BaseModel, Field, ValidationError
from rich import print


class EndpointArguments(BaseModel):
    """Arguments for an endpoint tag."""
    path: str = Field(..., description="API path for the endpoint.")
    http_method: Optional[str] = Field(None, description="HTTP method for the endpoint.")
    endpoint_title: Optional[str] = Field(None, description="Title for the endpoint.")
    endpoint_icon: Optional[str] = Field(None, description="Icon for the endpoint.")
    tips: Optional[List[str]] = Field(None, description="Tips to include in the documentation.")



class OpenApiDocsGenPlugin(BasePlugin):
    # Define configuration options
    config_scheme = (
        ("openapi_file", Type(str, required=True)),  # Path to OpenAPI spec file
    )

    def __init__(self):
        self.spec = None
        self.logger = get_plugin_logger(__name__)

    def on_config(self, config):
        """Load the OpenAPI spec during the config stage."""
        openapi_file = self.config.get("openapi_file")

        if not os.path.exists(openapi_file):
            raise FileNotFoundError(f"OpenAPI spec file '{openapi_file}' does not exist.")

        try:
            parser = ResolvingParser(openapi_file)
            self.spec = parser.specification  # Dictionary of the spec
            print(f"Successfully loaded OpenAPI spec from {openapi_file}")
        except Exception as e:
            print(f"Error loading OpenAPI spec: {e}")
            raise

        # DEV Add the OpenAPI file to MkDocs' watch list
        plugin_dir = os.path.dirname(__file__)
        if "watch" in config:
            config["watch"].append(plugin_dir)
        else:
            config["watch"] = [plugin_dir]


        # Log some basic details about the spec
        print(self.spec['info'].keys())
        self.logger.info(f"API Title: {self.spec['info']['title']}")
        self.logger.info(f"API Version: {self.spec['info']['version']}")
        self.logger.info(f"Available Paths: {', '.join(self.spec['paths'].keys())}")

    def extract_arguments(self, tag_content: str) -> EndpointArguments:
        """
        Extract arguments from the docs.endpoint block and return a validated Pydantic model.
        """
        arg_pattern = re.compile(r"^\s*(\w+):\s*(.*)$", re.MULTILINE)
        continuation_pattern = re.compile(r"^\s{4}(.+)$", re.MULTILINE)

        arguments = {}
        tips = []

        lines = tag_content.splitlines()
        current_key = None

        for line in lines:
            arg_match = arg_pattern.match(line)
            if arg_match:
                # Start of a new key-value pair
                key, value = arg_match.groups()
                current_key = key
                if value.strip():
                    arguments[key] = value.strip()
                elif key == "tips":
                    arguments[key] = []  # Initialize tips as a list
            elif current_key == "tips":
                # Collect continuation lines for "tips"
                continuation_match = continuation_pattern.match(line)
                if continuation_match:
                    tip = continuation_match.group(1).strip()
                    tips.append(tip)

        # Add tips to arguments
        if tips:
            arguments["tips"] = tips

        try:
            return EndpointArguments(**arguments)
        except ValidationError as e:
            raise ValueError(f"Invalid arguments in docs.endpoint: {e}")

    def on_page_markdown(self, markdown, page, config, files):
        """
        Process ::: docs.endpoint tags in Markdown.
        """
        # Match ::: docs. blocks
        docs_pattern = re.compile(r"::: docs\.endpoint\n(.*?)\n:::", re.DOTALL)

        def replace_docs_endpoint(match):
            """Extract arguments and generate documentation."""
            tag_content = match.group(1)

            # Extract arguments
            try:
                args = self.extract_arguments(tag_content)
                return self.generate_endpoint_docs(args)
            except ValueError as e:
                return f"**Error parsing docs.endpoint**: {e}"

        # Replace all matches in the Markdown
        return docs_pattern.sub(replace_docs_endpoint, markdown)

    @staticmethod
    def generate_tips_section(tips: List[str]) -> str:
        """Render a Tips section as a Markdown block."""
        if not tips:
            return ""
        tips_block = "!!! tip \"Method Tips\"\n"
        for tip in tips:
            tips_block += f"    {tip}\n"
        return tips_block

    def generate_endpoint_docs(self, args: EndpointArguments) -> str:
        """
        Generate documentation for the endpoint using the extracted arguments.
        """
        method_spec = self.spec['paths'].get(args.path).get(args.http_method.lower())
        docs = ""  # For building markdown content

        # H2 Endpoint Title
        if args.endpoint_title:
            docs += f"## <icon class=\"{args.endpoint_icon}\" />&nbsp; {args.endpoint_title} {{: data-toc-label=\"{args.endpoint_title}\" : .custom-header}}\n"

        # H3 Method and Path Title
        docs += f"""### <span class=\"http-{args.http_method.lower() or 'any'}\">{args.http_method or 'ANY'}</span>` {args.path}` -- {method_spec['summary']} {{ : data-toc-label=\"{args.http_method + ' ' +method_spec['summary']}\" : .styled-as-h2 }}\n\n"""

        docs += f"{method_spec['description']}\n\n"

        # Add the Tips section if provided
        if args.tips:
            print("GENERATING TIPS SECTION")
            docs += self.generate_tips_section(args.tips) + "\n\n"

        ### URL Parameters

        return docs
