package dev.openpycharm.frontend;

import com.intellij.openapi.options.ConfigurationException;
import com.intellij.openapi.options.SearchableConfigurable;
import com.intellij.openapi.project.Project;
import java.awt.BorderLayout;
import javax.swing.BorderFactory;
import javax.swing.Box;
import javax.swing.BoxLayout;
import javax.swing.JCheckBox;
import javax.swing.JComponent;
import javax.swing.JLabel;
import javax.swing.JPanel;

/** Native project settings; creating/resetting/applying this panel never reads the bundle. */
public final class FrontendProjectConfigurable implements SearchableConfigurable {
  private final FrontendProjectSettings settings;
  private JPanel panel;
  private JCheckBox enabled;
  public FrontendProjectConfigurable(Project project) { this(FrontendProjectSettings.getInstance(project)); }
  FrontendProjectConfigurable(FrontendProjectSettings settings) { this.settings = settings; }
  @Override public String getId() { return "dev.openpycharm.frontend.settings"; }
  @Override public String getDisplayName() { return "JavaScript and TypeScript"; }
  @Override public JComponent createComponent() {
    if (panel == null) {
      panel = new JPanel(new BorderLayout());
      JPanel contents = new JPanel(); contents.setLayout(new BoxLayout(contents, BoxLayout.Y_AXIS));
      contents.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
      enabled = new JCheckBox("Enable JavaScript and TypeScript language service in this project");
      contents.add(enabled); contents.add(Box.createVerticalStrut(12));
      contents.add(new JLabel(FrontendBundledRuntime.VERSION_LABEL));
      contents.add(Box.createVerticalStrut(8));
      contents.add(new JLabel("Runs locally for trusted project files. No runtime download is required."));
      panel.add(contents, BorderLayout.NORTH); reset();
    }
    return panel;
  }
  @Override public boolean isModified() { return enabled != null && (enabled.isSelected() != settings.enabled() || settings.restartPending()); }
  @Override public void apply() throws ConfigurationException {
    if (enabled == null) return;
    try { settings.setEnabled(enabled.isSelected()); }
    catch (RuntimeException error) {
      ConfigurationException failure = new ConfigurationException("Could not schedule the frontend language service restart; apply again to retry.");
      failure.initCause(error); throw failure;
    }
  }
  @Override public void reset() { if (enabled != null) enabled.setSelected(settings.enabled()); }
  @Override public void disposeUIResources() { panel = null; enabled = null; }
}
