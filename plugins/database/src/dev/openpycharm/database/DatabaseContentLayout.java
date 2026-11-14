package dev.openpycharm.database;

import java.awt.*;
import javax.swing.*;

/** Responsive native split panes; narrow/big-font layouts use full-width tabs. */
public final class DatabaseContentLayout extends JPanel {
  private final JComponent browser,browserActions,commands;
  private final QuerySplit query;
  private final JSplitPane horizontal;
  private final JTabbedPane tabs=new JTabbedPane();
  private boolean tabbed;
  public DatabaseContentLayout(JComponent browser,JComponent editor,JComponent commands,JComponent sql,JComponent results,JComponent browserActions){
    super(new BorderLayout());this.browser=browser;this.browserActions=browserActions;this.commands=commands;
    query=new QuerySplit(editor,commands,sql,results);
    horizontal=new JSplitPane(JSplitPane.HORIZONTAL_SPLIT,browser,query);horizontal.setResizeWeight(.25);horizontal.setDividerSize(8);horizontal.setContinuousLayout(true);add(horizontal,BorderLayout.CENTER);
  }
  static int actionsWidth(JComponent actions){int width=0;for(Component c:actions.getComponents())if(c.isVisible())width=Math.max(width,c.getPreferredSize().width);Insets i=actions.getInsets();return width+i.left+i.right+8;}
  @Override public void doLayout(){
    int browserWidth=Math.max(110,actionsWidth(browserActions)+2),queryWidth=actionsWidth(commands)+4;
    browser.setMinimumSize(new Dimension(browserWidth,100));
    boolean narrow=getWidth()>0&&getWidth()<browserWidth+queryWidth+horizontal.getDividerSize()+4;
    if(narrow!=tabbed){
      removeAll();
      if(narrow){horizontal.setLeftComponent(null);horizontal.setRightComponent(null);tabs.addTab("Tables",browser);tabs.addTab("SQL",query);tabs.setSelectedComponent(query);add(tabs,BorderLayout.CENTER);}
      else{tabs.removeAll();horizontal.setLeftComponent(browser);horizontal.setRightComponent(query);horizontal.setDividerLocation(Math.max(140,browserWidth));add(horizontal,BorderLayout.CENTER);}
      tabbed=narrow;
    }
    super.doLayout();
  }
  public boolean isTabbed(){return tabbed;}
  public JTabbedPane tabs(){return tabs;}
  public JSplitPane querySplit(){return query;}
  public JSplitPane browserSplit(){return horizontal;}
  private static final class QuerySplit extends JSplitPane {
    private final JComponent editor,commands,sql,results;
    QuerySplit(JComponent editor,JComponent commands,JComponent sql,JComponent results){
      super(JSplitPane.VERTICAL_SPLIT,editor,results);this.editor=editor;this.commands=commands;this.sql=sql;this.results=results;
      setResizeWeight(.5);setDividerSize(8);setContinuousLayout(true);
    }
    @Override public void doLayout(){
      Insets insets=getInsets();int width=Math.max(1,getWidth()-insets.left-insets.right);
      int toolbarHeight=commands.getLayout() instanceof DatabaseToolbarLayout wrap?wrap.preferredAtWidth(commands,width).height:commands.getPreferredSize().height;
      Insets editorInsets=editor.getInsets();int minWidth=actionsWidth(commands)+editorInsets.left+editorInsets.right;
      int minHeight=toolbarHeight+4+40+editorInsets.top+editorInsets.bottom;
      sql.setMinimumSize(new Dimension(100,40));results.setMinimumSize(new Dimension(100,40));editor.setMinimumSize(new Dimension(minWidth,minHeight));
      setMinimumSize(new Dimension(minWidth+insets.left+insets.right,minHeight+40+getDividerSize()+insets.top+insets.bottom));
      super.doLayout();
      int minimum=getUI().getMinimumDividerLocation(this),maximum=getUI().getMaximumDividerLocation(this),location=getDividerLocation();
      if(minimum>=0&&maximum>=minimum&&(location<minimum||location>maximum)){setDividerLocation(Math.max(minimum,Math.min(maximum,location)));super.doLayout();}
    }
  }
}
