package dev.openpycharm.notebooks;

import java.awt.*;
import javax.swing.*;
import javax.swing.table.*;

/** Only native Swing components receive prepared images, styled documents and table strings. */
public final class NotebookOutputPanel extends JPanel implements AutoCloseable {
  private NotebookRichOutput.Plan current;
  public NotebookOutputPanel() { setLayout(new BoxLayout(this, BoxLayout.Y_AXIS)); }
  /** Takes the caller's Plan reference. Parsing, image IO and markup never run here. */
  public void apply(NotebookRichOutput.Plan plan) {
    if (!SwingUtilities.isEventDispatchThread()) { plan.close(); throw new IllegalStateException("Preview components require the EDT"); }
    JPanel prepared = new JPanel(); prepared.setLayout(new BoxLayout(prepared, BoxLayout.Y_AXIS));
    try {
      for (NotebookRichOutput.Block block : plan.blocks()) {
        JComponent component;
        if (block instanceof NotebookRichOutput.Text text) {
          JTextPane pane = new JTextPane(text.document()); pane.setEditable(false);
          pane.setBorder(BorderFactory.createEmptyBorder(5, 8, 5, 8));
          component = pane;
        } else if (block instanceof NotebookRichOutput.Table data) component = table(data);
        else if (block instanceof NotebookRichOutput.Image image) {
          component = new JComponent() {
            @Override protected void paintComponent(Graphics graphics) {
              super.paintComponent(graphics);
              Graphics2D copy = (Graphics2D)graphics.create();
              try {
                copy.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
                copy.drawImage(image.image(), 0, 0, image.width(), image.height(), null);
              } finally { copy.dispose(); }
            }
          };
          component.setPreferredSize(new Dimension(image.width(), image.height()));
          component.setMinimumSize(component.getPreferredSize()); component.setMaximumSize(component.getPreferredSize());
          component.setToolTipText(image.mime() + " — " + image.sourceWidth() + " × " + image.sourceHeight());
        } else continue;
        component.setAlignmentX(Component.LEFT_ALIGNMENT); prepared.add(component);
      }
    } catch (RuntimeException error) { plan.close(); throw error; }
    NotebookRichOutput.Plan previous = current;
    current = plan; removeAll(); add(prepared); setVisible(!plan.blocks().isEmpty()); revalidate(); repaint();
    if (previous != null) previous.close();
  }
  private static JComponent table(NotebookRichOutput.Table data) {
    DefaultTableModel model = new DefaultTableModel(data.rows().stream().map(row -> row.toArray(String[]::new)).toArray(String[][]::new), data.headers().toArray(String[]::new)) {
      @Override public boolean isCellEditable(int row, int column) { return false; }
      @Override public Class<?> getColumnClass(int column) { return String.class; }
    };
    JTable table = new JTable(model); table.setAutoResizeMode(JTable.AUTO_RESIZE_OFF); table.setFillsViewportHeight(true);
    DefaultTableCellRenderer literal = new DefaultTableCellRenderer() {
      @Override protected void setValue(Object value) {
        putClientProperty("html.disable", Boolean.TRUE);
        // JLabel's implicit HTML detection is never allowed to interpret cell content.
        setText(" " + (value == null ? "" : value.toString()));
      }
    };
    table.setDefaultRenderer(String.class, literal); table.getTableHeader().setDefaultRenderer(literal);
    for (int i = 0; i < table.getColumnCount(); i++) table.getColumnModel().getColumn(i).setPreferredWidth(140);
    JScrollPane scroll = new JScrollPane(table);
    scroll.setPreferredSize(new Dimension(Math.min(980, Math.max(280, 140 * data.headers().size())), Math.min(320, 26 + Math.max(1, data.rows().size()) * table.getRowHeight())));
    scroll.setMaximumSize(new Dimension(Integer.MAX_VALUE, 320)); return scroll;
  }
  @Override public void close() {
    if (current != null) { current.close(); current = null; }
    removeAll();
  }
}
