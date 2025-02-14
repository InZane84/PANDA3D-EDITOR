import sys
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor
from PyQt5.QtWidgets import (
    QApplication,
    QGraphicsScene,
    QGraphicsView,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsEllipseItem,
    QGraphicsTextItem,
    QMainWindow,
    QDockWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QAction,
    QMenu
)

# -----------------------------------------------------------------------------
#   SocketItem: A clickable circle representing a node's input or output socket
# -----------------------------------------------------------------------------
class SocketItem(QGraphicsEllipseItem):
    def __init__(self, parent_node, socket_type="input", radius=6):
        """
        :param parent_node: The NodeItem that this socket belongs to
        :param socket_type: Either "input" or "output"
        :param radius: Radius of the socket circle
        """
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.setParentItem(parent_node)
        self.parent_node = parent_node
        self.socket_type = socket_type
        self.radius = radius

        # Style the socket
        self.setBrush(QBrush(QColor("#AAAAAA")))
        self.setPen(QPen(Qt.NoPen))

        # Allow clicking
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsFocusable)

    def mousePressEvent(self, event):
        """
        Start dragging a temporary edge if this is an output socket,
        or do nothing if it's an input socket.
        """
        if event.button() == Qt.LeftButton and self.socket_type == "output":
            # Forward this event to the scene, telling it we're starting a drag from this socket
            scene = self.scene()
            if hasattr(scene, "begin_edge_drag"):
                scene.begin_edge_drag(self)
        super().mousePressEvent(event)

# -----------------------------------------------------------------------------
#   NodeItem: Represents a draggable node in the scene
# -----------------------------------------------------------------------------
class NodeItem(QGraphicsRectItem):
    def __init__(self, title="Node", node_type="generic", width=120, height=60):
        super().__init__(0, 0, width, height)
        self.setBrush(QBrush(QColor("#4C4C4C")))
        self.setPen(QPen(Qt.NoPen))
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )

        self.title = title
        self.node_type = node_type
        self.width = width
        self.height = height

        # Title Text
        self.title_item = QGraphicsTextItem(self)
        self.title_item.setPlainText(self.title)
        self.title_item.setDefaultTextColor(Qt.white)
        self.title_item.setPos(5, 5)

        # Create sockets (1 input, 1 output)
        # Position them on the left/right edges, vertically centered
        self.input_socket = SocketItem(self, socket_type="input")
        self.input_socket.setPos(0, height / 2)

        self.output_socket = SocketItem(self, socket_type="output")
        self.output_socket.setPos(width, height / 2)

        # References to edges
        self.input_edge = None   # EdgeItem or None
        self.output_edge = None  # EdgeItem or None

    def boundingRect(self):
        return QRectF(0, 0, self.rect().width(), self.rect().height())
    
    def remove_edges(self):
        if self.input_edge:
            self.scene().removeItem(self.input_edge)
            self.input_edge = None
        if self.output_edge:
            self.scene().removeItem(self.output_edge)
            self.output_edge = None

    def itemChange(self, change, value):
        """
        Whenever this item moves, update edges if they exist.
        """
        if change == QGraphicsItem.ItemPositionHasChanged:
            if self.input_edge:
                self.input_edge.updatePositions()
            if self.output_edge:
                self.output_edge.updatePositions()
        return super().itemChange(change, value)

# -----------------------------------------------------------------------------
#   EdgeItem: Represents a connection (line) between two sockets of two nodes
# -----------------------------------------------------------------------------
class EdgeItem(QGraphicsItem):
    def __init__(self, start_socket, end_socket=None):
        super().__init__()
        self.start_socket = start_socket
        self.end_socket = end_socket  # can be None if we're currently dragging

        # Enable selecting the edge
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        # Make sure the line appears on top of nodes
        # (setZValue HIGHER than node’s default 0)
        self.setZValue(999)

        # Pens for different states
        self.normal_pen = QPen(QColor("#00FF00"))  # Bright green
        self.normal_pen.setWidth(3)
        self.selected_pen = QPen(QColor("#FFA500"))  # Orange
        self.selected_pen.setWidth(5)
        self.max_pen_width = max(self.normal_pen.width(), self.selected_pen.width())

        # If we already know the end_socket, set references
        if self.start_socket and self.end_socket:
            self.start_socket.parent_node.output_edge = self
            self.end_socket.parent_node.input_edge = self

        # We'll store the start/end points in scene coords
        self.start_point = QPointF()
        self.end_point = QPointF()

        self.updatePositions()

    def boundingRect(self):
        rect = QRectF(self.start_point, self.end_point).normalized()
        pen_width = self.max_pen_width
        rect = rect.adjusted(-pen_width, -pen_width, pen_width, pen_width)
        return rect

    def paint(self, painter, option, widget):
        if self.isSelected():
            painter.setPen(self.selected_pen)
        else:
            painter.setPen(self.normal_pen)
        painter.drawLine(self.start_point, self.end_point)

    def updatePositions(self):
        """
        Recompute the start_point and end_point in scene coordinates.
        """
        if self.start_socket:
            start_center = self.start_socket.parentItem().mapToScene(
                self.start_socket.pos()
            )
            self.start_point = self.mapFromScene(start_center)

        if self.end_socket:
            end_center = self.end_socket.parentItem().mapToScene(
                self.end_socket.pos()
            )
            self.end_point = self.mapFromScene(end_center)
        self.prepareGeometryChange()
        self.update()

    def setEndPos(self, pos):
        """
        While dragging, we set the end position to wherever the mouse is.
        """
        self.end_point = self.mapFromScene(pos)
        self.prepareGeometryChange()
        self.update()

    def finalizeConnection(self, end_socket):
        """
        Called when we release on a valid input socket.
        """
        self.end_socket = end_socket
        self.start_socket.parent_node.output_edge = self
        self.end_socket.parent_node.input_edge = self
        self.updatePositions()

# -----------------------------------------------------------------------------
#   NodeScene: The QGraphicsScene that manages nodes, edges, and dragging logic
# -----------------------------------------------------------------------------
class NodeScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(0, 0, 2000, 2000)
        self.temp_edge = None   # An EdgeItem we use while dragging
        self.drag_start_socket = None


    def contextMenuEvent(self, event):
        """Handle right-click to show context menu."""
        view = self.views()[0]
        item = self.itemAt(event.scenePos(), view.transform())
        main_window = self.parent()

        # Find if we clicked on text or any child item of a node
        node_item = None
        while item is not None:
            if isinstance(item, NodeItem):
                node_item = item
                break
            item = item.parentItem()

        # Adjust selection based on right-click
        if node_item:
            if not node_item.isSelected():
                self.clearSelection()
                node_item.setSelected(True)
        else:
            self.clearSelection()

        # Get selected nodes after adjustment
        selected_nodes = [n for n in self.selectedItems() if isinstance(n, NodeItem)]

        menu = QMenu()
        if selected_nodes:
            copy_action = QAction("Copy", menu)
            copy_action.triggered.connect(lambda: main_window.copy_nodes(selected_nodes))
            delete_action = QAction("Delete", menu)
            delete_action.triggered.connect(lambda: main_window.delete_items(selected_nodes))
            menu.addAction(copy_action)
            menu.addAction(delete_action)
        else:
            paste_action = QAction("Paste", menu)
            paste_action.triggered.connect(main_window.paste_nodes)
            paste_action.setEnabled(main_window.clipboard is not None)
            menu.addAction(paste_action)
            
        menu.exec_(event.screenPos())

    def begin_edge_drag(self, start_socket):
        """
        Called when the user clicks an output socket. 
        We'll create a temp_edge that follows the mouse until release.
        """
        if start_socket.parent_node.output_edge is not None:
            # We already have an output edge from this node
            return

        self.drag_start_socket = start_socket

        self.temp_edge = EdgeItem(start_socket, None)
        # Convert start socket center to scene coords
        start_center = start_socket.parentItem().mapToScene(start_socket.pos())
        self.temp_edge.start_point = self.temp_edge.mapFromScene(start_center)
        self.temp_edge.end_point = self.temp_edge.start_point
        self.addItem(self.temp_edge)

    def mouseMoveEvent(self, event):
        """
        If we're dragging a temporary edge, update its end position.
        """
        if self.temp_edge:
            scene_pos = event.scenePos()
            self.temp_edge.setEndPos(scene_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        If we release over an input socket, finalize the connection.
        Otherwise, remove the temp edge.
        """
        if self.temp_edge:
            released_items = self.items(event.scenePos())
            end_socket = None
            for item in released_items:
                if isinstance(item, SocketItem) and item.socket_type == "input":
                    # Found an input socket
                    # Check if it already has an input edge
                    if item.parent_node.input_edge is None:
                        end_socket = item
                        break

            if end_socket:
                # Finalize
                self.temp_edge.finalizeConnection(end_socket)
            else:
                # Discard
                self.removeItem(self.temp_edge)

            self.temp_edge = None
            self.drag_start_socket = None

        super().mouseReleaseEvent(event)

# -----------------------------------------------------------------------------
#   NodeView: QGraphicsView to hold the NodeScene (with panning/zooming)
# -----------------------------------------------------------------------------
class NodeView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setFocusPolicy(Qt.StrongFocus)  # Add this line
        self.setRenderHint(QPainter.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.RubberBandDrag)

    def wheelEvent(self, event):
        """Zoom in/out with the mouse wheel."""
        zoomInFactor = 1.25
        zoomOutFactor = 1 / zoomInFactor

        if event.angleDelta().y() > 0:
            zoomFactor = zoomInFactor
        else:
            zoomFactor = zoomOutFactor

        self.scale(zoomFactor, zoomFactor)

    def keyPressEvent(self, event):
        """Handle key press events, specifically the Delete key."""
        if event.key() == Qt.Key_Delete:
            # Directly call delete method on MainWindow
            if isinstance(self.parent(), MainWindow):
                self.parent().delete_selected_nodes()
        else:
            super().keyPressEvent(event)

# -----------------------------------------------------------------------------
#   MainWindow: The top-level window with a toolbox and the node editor
# -----------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Node Editor - CLEAR Lines (PyQt5)")

        # Clipboard to store copied nodes
        self.clipboard = None

        # Create Scene & View
        self.scene = NodeScene(self)
        self.view = NodeView(self.scene, self)
        self.setCentralWidget(self.view)

        # Create a right-side panel with buttons
        self.toolbox = QWidget()
        self.toolbox_layout = QVBoxLayout()
        self.toolbox.setLayout(self.toolbox_layout)

        # Buttons for adding nodes
        self.add_for_btn = QPushButton("Add For Node")
        self.add_for_btn.clicked.connect(self.add_for_node)  # Fixed method name
        self.toolbox_layout.addWidget(self.add_for_btn)

        self.add_if_btn = QPushButton("Add If Node")
        self.add_if_btn.clicked.connect(self.add_if_node)  # Fixed method name
        self.toolbox_layout.addWidget(self.add_if_btn)

        self.add_else_btn = QPushButton("Add Else Node")
        self.add_else_btn.clicked.connect(self.add_else_node)  # Fixed method name
        self.toolbox_layout.addWidget(self.add_else_btn)

        self.add_while_btn = QPushButton("Add While Node")
        self.add_while_btn.clicked.connect(self.add_while_node)  # Fixed method name
        self.toolbox_layout.addWidget(self.add_while_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_selected_nodes)
        self.toolbox_layout.addWidget(self.delete_btn)
        self.delete_btn.setEnabled(False)

        self.scene.selectionChanged.connect(self.update_delete_button_state)

        # Button for generating code
        self.generate_code_btn = QPushButton("Generate Code")
        self.generate_code_btn.clicked.connect(self.generate_code)
        self.toolbox_layout.addWidget(self.generate_code_btn)

        # Dock setup
        dock = QDockWidget("Toolbox", self)
        dock.setWidget(self.toolbox)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        self.resize(1200, 800)


    # -------------------------------------------------------------------------
    #   Context Menu: Copy, Paste, Delete
    # -------------------------------------------------------------------------
    def copy_nodes(self, nodes):
        """Copy selected nodes and their connecting edges to clipboard."""
        if not nodes:
            return
        self.clipboard = {'nodes': [], 'edges': []}
        copied_nodes = nodes  # List of NodeItem instances
        for node in copied_nodes:
            node_data = {
                'type': node.node_type,
                'title': node.title,
                'pos': node.pos(),
                'width': node.width,
                'height': node.height
            }
            self.clipboard['nodes'].append(node_data)
        
        # Collect edges that connect two nodes within the copied selection
        edges = []
        for i, source_node in enumerate(copied_nodes):
            if source_node.output_edge:
                edge = source_node.output_edge
                end_node = edge.end_socket.parent_node
                if end_node in copied_nodes:
                    j = copied_nodes.index(end_node)
                    edges.append({'source': i, 'target': j})
        self.clipboard['edges'] = edges

    def paste_nodes(self):
        """Paste nodes and edges from clipboard with an offset."""
        if not self.clipboard or 'nodes' not in self.clipboard:
            return
        delta = QPointF(20, 20)  # Offset for pasting
        new_nodes = []
        for node_data in self.clipboard['nodes']:
            node = NodeItem(
                title=node_data['title'],
                node_type=node_data['type'],
                width=node_data['width'],
                height=node_data['height']
            )
            node.setPos(node_data['pos'] + delta)
            self.scene.addItem(node)
            new_nodes.append(node)
        
        # Recreate the edges between pasted nodes
        for edge_data in self.clipboard['edges']:
            source_idx = edge_data['source']
            target_idx = edge_data['target']
            source_node = new_nodes[source_idx]
            target_node = new_nodes[target_idx]
            # Create a new edge between the output and input sockets
            edge = EdgeItem(source_node.output_socket, target_node.input_socket)
            self.scene.addItem(edge)
        
        # Select the new nodes
        for node in new_nodes:
            node.setSelected(True)

    def delete_items(self, items):
        """Delete specified items (nodes or edges) and their connections."""
        for item in items:
            if isinstance(item, NodeItem):
                # Remove input edge
                if item.input_edge:
                    edge = item.input_edge
                    source_node = edge.start_socket.parent_node
                    source_node.output_edge = None
                    self.scene.removeItem(edge)
                # Remove output edge
                if item.output_edge:
                    edge = item.output_edge
                    target_node = edge.end_socket.parent_node
                    target_node.input_edge = None
                    self.scene.removeItem(edge)
                # Remove the node
                self.scene.removeItem(item)
            elif isinstance(item, EdgeItem):
                # Update both connected nodes
                if item.start_socket:
                    item.start_socket.parent_node.output_edge = None
                if item.end_socket:
                    item.end_socket.parent_node.input_edge = None
                self.scene.removeItem(item)


    # -------------------------------------------------------------------------
    #   Delete functionality
    # -------------------------------------------------------------------------
    def update_delete_button_state(self):
        """Enable delete button if nodes or edges are selected."""
        selected_items = self.scene.selectedItems()
        has_deletable = any(isinstance(item, (NodeItem, EdgeItem)) for item in selected_items)
        self.delete_btn.setEnabled(has_deletable)

    def delete_selected_nodes(self):
        """Handle deletion of selected nodes and edges."""
        selected_items = self.scene.selectedItems()
        self.delete_items(selected_items)
        for item in selected_items:
            if isinstance(item, NodeItem):
                # Remove input edge (edge coming into this node)
                if item.input_edge:
                    edge = item.input_edge
                    # Update the source node's output_edge
                    source_node = edge.start_socket.parent_node
                    source_node.output_edge = None
                    self.scene.removeItem(edge)
                # Remove output edge (edge going out from this node)
                if item.output_edge:
                    edge = item.output_edge
                    # Update the target node's input_edge
                    target_node = edge.end_socket.parent_node
                    target_node.input_edge = None
                    self.scene.removeItem(edge)
                # Remove the node itself
                self.scene.removeItem(item)
            elif isinstance(item, EdgeItem):
                # Update both connected nodes
                if item.start_socket:
                    item.start_socket.parent_node.output_edge = None
                if item.end_socket:
                    item.end_socket.parent_node.input_edge = None
                self.scene.removeItem(item)

    # -------------------------------------------------------------------------
    #   Node creation methods (PROPERLY INDENTED INSIDE CLASS)
    # -------------------------------------------------------------------------
    def add_for_node(self):
        node = NodeItem(title="For Loop", node_type="for")
        self.scene.addItem(node)
        center = self.view.mapToScene(self.view.viewport().rect().center())
        node.setPos(center)

    def add_if_node(self):
        node = NodeItem(title="If Statement", node_type="if")
        self.scene.addItem(node)
        center = self.view.mapToScene(self.view.viewport().rect().center())
        node.setPos(center)

    def add_else_node(self):
        node = NodeItem(title="Else", node_type="else")
        self.scene.addItem(node)
        center = self.view.mapToScene(self.view.viewport().rect().center())
        node.setPos(center)

    def add_while_node(self):
        node = NodeItem(title="While Loop", node_type="while")
        self.scene.addItem(node)
        center = self.view.mapToScene(self.view.viewport().rect().center())
        node.setPos(center)

    # -------------------------------------------------------------------------
    #   Code Generation
    # -------------------------------------------------------------------------
    def generate_code(self):
        """
        Demonstrates a simple traversal from top-level nodes (no input_edge)
        to produce textual pseudocode. We follow each node's output edge
        down the chain. Indentation is increased for for/if/while, but
        'else' shares the same indent as 'if'.
        """
        all_nodes = [
            item for item in self.scene.items()
            if isinstance(item, NodeItem)
        ]

        # Find nodes with no input_edge => top-level
        top_level_nodes = [n for n in all_nodes if n.input_edge is None]

        generated_lines = []
        visited = set()

        def traverse(node, indent_level=0):
            if node in visited:
                return
            visited.add(node)
            indent = "    " * indent_level
            code_line = ""
            if node.node_type == "for":
                code_line = f"{indent}for i in range(0, 10):  # Example range"
            elif node.node_type == "if":
                code_line = f"{indent}if condition:  # Example condition"
            elif node.node_type == "else":
                code_line = f"{indent}else:"
            elif node.node_type == "while":
                code_line = f"{indent}while condition:  # Example condition"
            else:
                code_line = f"{indent}# Unknown node type"

            generated_lines.append(code_line)

            # If we have an output edge, follow it
            if node.output_edge:
                next_node = node.output_edge.end_socket.parent_node
                if node.node_type in ["for", "if", "while"]:
                    traverse(next_node, indent_level + 1)
                elif node.node_type == "else":
                    # else shares indent level with if
                    traverse(next_node, indent_level)
                else:
                    traverse(next_node, indent_level)

        for n in top_level_nodes:
            traverse(n, 0)

        # Print out the generated code in console
        print("Generated Code:\n")
        for line in generated_lines:
            print(line)

# -----------------------------------------------------------------------------
#   Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
