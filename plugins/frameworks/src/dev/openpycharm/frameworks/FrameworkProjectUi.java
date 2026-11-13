package dev.openpycharm.frameworks;

import com.intellij.ui.components.JBCheckBox;
import com.intellij.ui.dsl.builder.Panel;
import com.intellij.ui.dsl.builder.Row;
import com.jetbrains.python.newProjectWizard.PyV3ProjectTypeSpecificUI;

/** Small native addition; the base Python wizard owns path, interpreter and venv UI. */
public final class FrameworkProjectUi implements PyV3ProjectTypeSpecificUI<FrameworkProjectSettings> {
  @Override public void configureUpperPanel(FrameworkProjectSettings settings, Row row, Panel panel) {
    settings.setInstallDependencies(false);
    JBCheckBox install = new JBCheckBox("Install " + settings.framework().displayName() + " dependencies in the selected interpreter", false);
    install.setToolTipText("Creates requirements.txt in every case. Package installation runs only when this option is selected.");
    install.addActionListener(event -> settings.setInstallDependencies(install.isSelected()));
    row.cell(install);
  }
}
