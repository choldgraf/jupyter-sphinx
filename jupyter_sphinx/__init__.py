"""Simple sphinx extension that executes code in jupyter and inserts output."""

from ._version import version_info, __version__
from sphinx.util import logging
import docutils
import ipywidgets
import os
from sphinx.util.fileutil import copy_asset
from sphinx.errors import ExtensionError
from IPython.lib.lexers import IPythonTracebackLexer, IPython3Lexer

from .ast import (
    JupyterCell,
    JupyterCellNode,
    CellInputNode,
    CellOutputNode,
    CellOutputBundleNode,
    JupyterKernelNode,
    JupyterWidgetViewNode,
    JupyterWidgetStateNode,
    WIDGET_VIEW_MIMETYPE,
    JupyterDownloadRole,
    CellOutputsToNodes,
)
from .execute import JupyterKernel, ExecuteJupyterCells

REQUIRE_URL_DEFAULT = (
    "https://cdnjs.cloudflare.com/ajax/libs/require.js/2.3.4/require.min.js"
)

logger = logging.getLogger(__name__)

##############################################################################
# Constants and functions we'll use later

# Used for nodes that do not need to be rendered
def skip(self, node):
    raise docutils.nodes.SkipNode


# Used for nodes that should be gone by rendering time (OutputMimeBundleNode)
def halt(self, node):
    raise ExtensionError(
        (
            "Rendering encountered a node type that should "
            "have been removed before rendering: %s" % type(node)
        )
    )


# Renders the children of a container
render_container = (
    lambda self, node: self.visit_container(node),
    lambda self, node: self.depart_container(node),
)

# Used to render the container and its children as HTML
def visit_container_html(self, node):
    self.body.append(node.visit_html())
    self.visit_container(node)


def depart_container_html(self, node):
    self.depart_container(node)
    self.body.append(node.depart_html())


# Used to render an element node as HTML
def visit_element_html(self, node):
    self.body.append(node.html())
    raise docutils.nodes.SkipNode


##############################################################################
# Sphinx callback functions
def builder_inited(app):
    """
    2 cases
    case 1: ipywidgets 7, with require
    case 2: ipywidgets 7, no require
    """
    require_url = app.config.jupyter_sphinx_require_url
    if require_url:
        app.add_js_file(require_url)
        embed_url = (
            app.config.jupyter_sphinx_embed_url
            or ipywidgets.embed.DEFAULT_EMBED_REQUIREJS_URL
        )
    else:
        embed_url = (
            app.config.jupyter_sphinx_embed_url
            or ipywidgets.embed.DEFAULT_EMBED_SCRIPT_URL
        )
    if embed_url:
        app.add_js_file(embed_url)

    # add jupyter-sphinx css
    app.add_css_file("jupyter-sphinx.css")


def build_finished(app, env):
    if app.builder.format != "html":
        return

    # Copy stylesheet
    src = os.path.join(os.path.dirname(__file__), "css")
    dst = os.path.join(app.outdir, "_static")
    copy_asset(src, dst)


##############################################################################
# Main setup
def setup(app):
    """A temporary setup function so that we can use it here and in execute.

    This should be removed and converted into `setup` after a deprecation
    cycle.
    """
    # Configuration

    app.add_config_value(
        "jupyter_execute_kwargs",
        dict(timeout=-1, allow_errors=True, store_widget_state=True),
        "env",
    )
    app.add_config_value("jupyter_execute_default_kernel", "python3", "env")
    app.add_config_value(
        "jupyter_execute_data_priority",
        [
            WIDGET_VIEW_MIMETYPE,
            "application/javascript",
            "text/html",
            "image/svg+xml",
            "image/png",
            "image/jpeg",
            "text/latex",
            "text/plain",
        ],
        "env",
    )

    # ipywidgets config
    app.add_config_value("jupyter_sphinx_require_url", REQUIRE_URL_DEFAULT, "html")
    app.add_config_value("jupyter_sphinx_embed_url", None, "html")

    # linenos config
    app.add_config_value("jupyter_sphinx_linenos", False, "env")
    app.add_config_value("jupyter_sphinx_continue_linenos", False, "env")

    # JupyterKernelNode is just a doctree marker for the
    # ExecuteJupyterCells transform, so we don't actually render it.
    app.add_node(
        JupyterKernelNode,
        html=(skip, None),
        latex=(skip, None),
        textinfo=(skip, None),
        text=(skip, None),
        man=(skip, None),
    )

    # Register our container nodes, these should behave just like a regular container
    for node in [JupyterCellNode, CellInputNode, CellOutputNode]:
        app.add_node(
            node,
            override=True,
            html=(render_container),
            latex=(render_container),
            textinfo=(render_container),
            text=(render_container),
            man=(render_container),
        )

    # Register the output bundle node.
    # No translators should touch this node because we'll replace it in a post-transform
    app.add_node(
        CellOutputBundleNode,
        override=True,
        html=(halt, None),
        latex=(halt, None),
        textinfo=(halt, None),
        text=(halt, None),
        man=(halt, None),
    )

    # JupyterWidgetViewNode holds widget view JSON,
    # but is only rendered properly in HTML documents.
    app.add_node(
        JupyterWidgetViewNode,
        html=(visit_element_html, None),
        latex=(skip, None),
        textinfo=(skip, None),
        text=(skip, None),
        man=(skip, None),
    )
    # JupyterWidgetStateNode holds the widget state JSON,
    # but is only rendered in HTML documents.
    app.add_node(
        JupyterWidgetStateNode,
        html=(visit_element_html, None),
        latex=(skip, None),
        textinfo=(skip, None),
        text=(skip, None),
        man=(skip, None),
    )

    app.add_directive("jupyter-execute", JupyterCell)
    app.add_directive("jupyter-kernel", JupyterKernel)
    app.add_role("jupyter-download:notebook", JupyterDownloadRole())
    app.add_role("jupyter-download:nb", JupyterDownloadRole())
    app.add_role("jupyter-download:script", JupyterDownloadRole())
    app.add_transform(ExecuteJupyterCells)
    app.add_post_transform(CellOutputsToNodes)

    # For syntax highlighting
    app.add_lexer("ipythontb", IPythonTracebackLexer())
    app.add_lexer("ipython", IPython3Lexer())

    app.connect("builder-inited", builder_inited)
    app.connect("build-finished", build_finished)

    return {"version": __version__, "parallel_read_safe": True}
