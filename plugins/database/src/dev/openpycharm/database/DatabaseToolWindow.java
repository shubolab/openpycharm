package dev.openpycharm.database;

import com.intellij.openapi.Disposable;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.editor.Editor;
import com.intellij.openapi.editor.EditorFactory;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.ui.DialogWrapper;
import com.intellij.openapi.ui.Messages;
import com.intellij.openapi.wm.ToolWindow;
import com.intellij.openapi.wm.ToolWindowFactory;
import com.intellij.ui.EditorTextField;
import com.intellij.ui.components.JBScrollPane;
import com.intellij.ui.components.JBList;
import com.intellij.ui.table.JBTable;
import com.intellij.ui.content.ContentFactory;
import com.intellij.util.ui.JBUI;
import javax.swing.*;
import javax.swing.table.DefaultTableCellRenderer;
import javax.swing.table.DefaultTableModel;
import java.awt.*;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.function.Consumer;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

/** Native IntelliJ editor and Swing result grid. JDBC/PasswordSafe never run on EDT. */
public final class DatabaseToolWindow implements ToolWindowFactory {
  @Override public void createToolWindowContent(@NotNull Project project,@NotNull ToolWindow window) {
    Panel panel=new Panel(project);
    var content=ContentFactory.getInstance().createContent(panel,"Console",false);
    content.setDisposer(panel);window.getContentManager().addContent(content);
  }
  public static final class Panel extends JPanel implements Disposable {
    private final Project project;
    private final DatabaseService service;
    private final JComboBox<DatabaseProfile> profiles=new JComboBox<>();
    private final DefaultListModel<JdbcSession.Table> tableModel=new DefaultListModel<>();
    private final JBList<JdbcSession.Table> tables=new JBList<>(tableModel);
    private final JBTable grid=new JBTable();
    private final JLabel status=new JLabel("Add a data source, then connect. Query limit: 500 rows / 15 seconds.");
    private final EditorTextField sql;
    private final JButton add=new JButton("+"),edit=new JButton("Edit"),remove=new JButton("Remove"),connect=new JButton("Connect"),disconnect=new JButton("Disconnect"),
      refresh=new JButton("Refresh tables"),columns=new JButton("Columns"),select=new JButton("Select rows"),run=new JButton("Run statement"),cancel=new JButton("Cancel"),
      begin=new JButton("Begin transaction"),commit=new JButton("Commit"),rollback=new JButton("Rollback");
    private boolean connected,manual,disposed;
    public Panel(Project project) {
      super(new BorderLayout(0,6));this.project=project;service=DatabaseService.get(project);setBorder(JBUI.Borders.empty(6));
      sql=new EditorTextField(EditorFactory.getInstance().createDocument("-- Run the statement at the caret, or select one statement.\nSELECT 1 AS ready;\n"),project,SqlLanguage.FileType.INSTANCE,false,false);
      sql.setDisposedWith(this);sql.addSettingsProvider(e->{e.getSettings().setLineNumbersShown(true);e.getSettings().setUseSoftWraps(false);});
      sql.setPreferredSize(new Dimension(700,200));
      JPanel top=new JPanel(new FlowLayout(FlowLayout.LEFT,5,0));for(JComponent c:List.of(profiles,add,edit,remove,connect,disconnect))top.add(c);add(top,BorderLayout.NORTH);
      JPanel editor=new JPanel(new BorderLayout(0,4));editor.add(sql,BorderLayout.CENTER);
      JPanel commands=new JPanel(new FlowLayout(FlowLayout.LEFT,4,0));for(JButton c:List.of(run,cancel,begin,commit,rollback))commands.add(c);editor.add(commands,BorderLayout.NORTH);
      grid.setAutoResizeMode(JTable.AUTO_RESIZE_OFF);grid.setAutoCreateRowSorter(true);
      grid.setDefaultRenderer(Object.class,new DefaultTableCellRenderer(){@Override protected void setValue(Object v){super.setValue(v==null?"NULL":v);}});
      JSplitPane vertical=new JSplitPane(JSplitPane.VERTICAL_SPLIT,editor,new JBScrollPane(grid));vertical.setResizeWeight(.5);
      JPanel browser=new JPanel(new BorderLayout(0,4));browser.add(new JBScrollPane(tables),BorderLayout.CENTER);
      JPanel browseButtons=new JPanel(new GridLayout(0,1,2,2));for(JButton c:List.of(refresh,columns,select))browseButtons.add(c);browser.add(browseButtons,BorderLayout.SOUTH);
      browser.setPreferredSize(new Dimension(230,400));
      JSplitPane horizontal=new JSplitPane(JSplitPane.HORIZONTAL_SPLIT,browser,vertical);horizontal.setResizeWeight(.22);add(horizontal,BorderLayout.CENTER);add(status,BorderLayout.SOUTH);
      reload(null);
      profiles.addActionListener(e->update());
      add.addActionListener(e->profile(null));edit.addActionListener(e->profile(selected()));
      remove.addActionListener(e->{DatabaseProfile p=selected();if(p!=null&&Messages.showYesNoDialog(project,"Remove connection profile “"+p.name+"” and its saved password?","Remove data source",Messages.getQuestionIcon())==Messages.YES)
        task(()->{service.remove(p);return null;},v->{reload(null);status.setText("Connection profile removed.");});});
      connect.addActionListener(e->{DatabaseProfile p=selected();if(p!=null)task(()->{try{service.connect(p);return service.session.tables();}catch(Exception ex){try{service.session.close();}catch(Exception close){ex.addSuppressed(close);}throw ex;}},v->{connected=true;manual=false;showTables(v);status.setText("Connected to "+p.name+" · Auto commit");});});
      disconnect.addActionListener(e->task(()->{service.session.close();return null;},v->{connected=false;manual=false;tableModel.clear();status.setText("Disconnected. Any open transaction was rolled back.");}));
      refresh.addActionListener(e->task(service.session::tables,this::showTables));
      columns.addActionListener(e->{JdbcSession.Table t=tables.getSelectedValue();if(t!=null)task(()->service.session.columns(t),this::showResult);});
      select.addActionListener(e->{JdbcSession.Table t=tables.getSelectedValue();if(t!=null)task(()->service.session.selectSql(t),text->{ApplicationManager.getApplication().runWriteAction(()->sql.setText(text));status.setText("Review the generated SQL, then run it.");});});
      run.addActionListener(e->runConsole());
      cancel.addActionListener(e->{service.cancel(this::failure);status.setText("Cancellation requested; waiting for the driver.");});
      begin.addActionListener(e->task(()->{service.session.setAutoCommit(false);return null;},v->{manual=true;status.setText("Manual transaction · Commit or Rollback when finished");}));
      commit.addActionListener(e->transaction(true));rollback.addActionListener(e->transaction(false));
      tables.addListSelectionListener(e->update());update();
    }
    private DatabaseProfile selected(){return (DatabaseProfile)profiles.getSelectedItem();}
    private void reload(String id){profiles.removeAllItems();for(DatabaseProfile p:service.profiles()){profiles.addItem(p);if(java.util.Objects.equals(p.id,id))profiles.setSelectedItem(p);}update();}
    private void profile(DatabaseProfile original){
      if(original!=null){try{original.validate();}catch(RuntimeException e){failure(e);return;}}
      ProfileDialog dialog=new ProfileDialog(project,original);
      if(!dialog.showAndGet())return;
      DatabaseProfile p=dialog.profile;char[] secret=dialog.password.getPassword();dialog.password.setText("");
      boolean forget=dialog.forget.isSelected();
      task(()->{service.save(p,secret,forget);return null;},v->{reload(p.id);status.setText("Saved connection profile. Password storage follows IDE PasswordSafe settings.");});
    }
    private void transaction(boolean save){task(()->{if(save)service.session.commit();else service.session.rollback();service.session.setAutoCommit(true);return null;},v->{manual=false;status.setText((save?"Committed":"Rolled back")+" · Auto commit");});}
    public void runSql(String text){if(!connected){status.setText("Connect a data source in Database before running SQL.");return;}task(()->service.session.execute(text),this::showResult);}
    private void runConsole(){try{Editor e=sql.getEditor();String selection=e==null?null:e.getSelectionModel().getSelectedText();runSql(selection==null?SqlText.atCaret(sql.getText(),e==null?0:e.getCaretModel().getOffset()):selection);}catch(RuntimeException ex){failure(ex);}}
    private <T> void task(Callable<T> action,Consumer<T> success){
      if(service.busy()){status.setText("Wait for the current operation, or cancel the query.");return;}
      status.setText("Working…");service.submit(action,v->{success.accept(v);update();},e->{failure(e);update();});update();
    }
    private void failure(Throwable e){String message=e.getMessage();if(message==null)message=e.getClass().getSimpleName();message=message.replace('\n',' ').replace('\r',' ');status.setText("Database: "+message.substring(0,Math.min(message.length(),700)));}
    private void showTables(List<JdbcSession.Table> rows){tableModel.clear();for(var row:rows)tableModel.addElement(row);status.setText(rows.size()+" tables/views (maximum 500). Select one for columns or a SELECT statement.");}
    private void showResult(JdbcSession.Result r){
      Object[][] rows=r.rows().stream().map(List::toArray).toArray(Object[][]::new);
      grid.setModel(new DefaultTableModel(rows,r.columns().toArray()){@Override public boolean isCellEditable(int row,int column){return false;}});
      for(int i=0;i<grid.getColumnCount();i++)grid.getColumnModel().getColumn(i).setPreferredWidth(160);
      status.setText((r.updateCount()<0?r.rows().size()+" rows":r.updateCount()+" rows affected")+" · "+r.elapsedMillis()+" ms"+(r.truncated()?" · Preview truncated":"")+(manual?" · Uncommitted transaction":" · Auto commit"));
    }
    private void update(){boolean idle=!service.busy();boolean profile=selected()!=null;boolean valid=profile;try{if(profile)selected().validate();}catch(RuntimeException e){valid=false;}
      profiles.setEnabled(idle&&!connected);add.setEnabled(idle&&!connected);edit.setEnabled(idle&&!connected&&profile);remove.setEnabled(idle&&!connected&&profile);connect.setEnabled(idle&&!connected&&valid);disconnect.setEnabled(idle&&connected);
      run.setEnabled(idle&&connected);cancel.setEnabled(!idle);refresh.setEnabled(idle&&connected);columns.setEnabled(idle&&connected&&tables.getSelectedValue()!=null);select.setEnabled(columns.isEnabled());
      begin.setEnabled(idle&&connected&&!manual);commit.setEnabled(idle&&connected&&manual);rollback.setEnabled(idle&&connected&&manual);
    }
    @Override public void dispose(){disposed=true;}
  }
  private static final class ProfileDialog extends DialogWrapper {
    private final DatabaseProfile profile;
    private final JTextField name=new JTextField(),file=new JTextField(),host=new JTextField(),port=new JTextField(),database=new JTextField(),user=new JTextField();
    private final JComboBox<DatabaseProfile.Engine> engine=new JComboBox<>(DatabaseProfile.Engine.values());
    private final JPasswordField password=new JPasswordField();
    private final JCheckBox tls=new JCheckBox("Verify TLS certificate and hostname (network databases)",true),forget=new JCheckBox("Forget saved password");
    ProfileDialog(Project project,DatabaseProfile original){
      super(project);profile=original==null?new DatabaseProfile():original.copy();if(original==null)profile.file=(project.getBasePath()==null?System.getProperty("user.home"):project.getBasePath())+"/database.sqlite";
      name.setText(profile.name);engine.setSelectedItem(profile.kind());file.setText(profile.file);host.setText(profile.host);port.setText(Integer.toString(profile.port));database.setText(profile.database);user.setText(profile.user);tls.setSelected(profile.verifyTls);
      engine.addActionListener(e->{if(engine.getSelectedItem()==DatabaseProfile.Engine.MYSQL&&port.getText().equals("5432"))port.setText("3306");else if(engine.getSelectedItem()==DatabaseProfile.Engine.POSTGRESQL&&port.getText().equals("3306"))port.setText("5432");fields();});
      setTitle(original==null?"New data source":"Edit data source");init();fields();
    }
    private void fields(){boolean network=engine.getSelectedItem()!=DatabaseProfile.Engine.SQLITE;file.setEnabled(!network);for(JComponent c:List.of(host,port,database,user,password,tls,forget))c.setEnabled(network);}
    @Override protected @Nullable JComponent createCenterPanel(){
      JPanel p=new JPanel(new GridBagLayout());p.setPreferredSize(new Dimension(620,370));int row=0;
      for(Object[] entry:new Object[][]{{"Name",name},{"Engine",engine},{"SQLite absolute file",file},{"Host",host},{"Port",port},{"Database",database},{"User",user},{"New password (blank keeps saved)",password},{"",tls},{"",forget}}){
        GridBagConstraints c=new GridBagConstraints();c.gridx=0;c.gridy=row;c.anchor=GridBagConstraints.WEST;c.insets=JBUI.insets(3);p.add(new JLabel((String)entry[0]),c);c.gridx=1;c.weightx=1;c.fill=GridBagConstraints.HORIZONTAL;p.add((JComponent)entry[1],c);row++;
      }
      return p;
    }
    @Override protected void doOKAction(){try{profile.name=name.getText().trim();profile.engine=((DatabaseProfile.Engine)engine.getSelectedItem()).name();profile.file=file.getText().trim();profile.host=host.getText().trim();profile.port=profile.kind()==DatabaseProfile.Engine.SQLITE?5432:Integer.parseInt(port.getText().trim());profile.database=database.getText();profile.user=user.getText();profile.verifyTls=tls.isSelected();profile.validate();super.doOKAction();}catch(RuntimeException e){setErrorText(e.getMessage());}}
    @Override public void doCancelAction(){char[] data=password.getPassword();Arrays.fill(data,'\0');password.setText("");super.doCancelAction();}
  }
}
