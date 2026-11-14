package dev.openpycharm.database;

import java.awt.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import javax.swing.*;

/** Offscreen native Swing geometry only: no Window, IDE, network or JDBC. */
public final class DatabaseLayoutProbe {
  private static int checks;
  private static void check(boolean condition,String message){checks++;if(!condition)throw new AssertionError(message);}
  private static void row(int width,String... names){
    JButton[] buttons=Arrays.stream(names).map(JButton::new).toArray(JButton[]::new);AtomicInteger clicks=new AtomicInteger();for(JButton b:buttons)b.addActionListener(e->clicks.incrementAndGet());
    JPanel panel=DatabaseToolbarLayout.row(buttons);panel.setSize(width,1);Dimension preferred=panel.getPreferredSize();panel.setSize(width,preferred.height);panel.doLayout();
    for(JButton b:buttons){Rectangle bounds=b.getBounds();check(bounds.x>=0&&bounds.y>=0&&bounds.x+bounds.width<=width&&bounds.y+bounds.height<=panel.getHeight(),"button clipped at "+width+": "+b.getText()+" "+bounds);check(bounds.width>=b.getPreferredSize().width,"button text width clipped");b.doClick(0);}
    check(clicks.get()==buttons.length,"all toolbar actions remain reachable");
    if(width==320)check(preferred.height>buttons[0].getPreferredSize().height,"narrow toolbar reserves its additional wrapped rows");
    panel.setSize(700,1);panel.setSize(700,panel.getPreferredSize().height);panel.doLayout();for(JButton b:buttons)check(b.getY()+b.getHeight()<=panel.getHeight(),"growing width relayout remains reachable");
  }
  private static void layout(Container c){c.doLayout();for(Component child:c.getComponents())if(child instanceof Container nested)layout(nested);}
  private static JButton button(String text,float scale){JButton b=new JButton(text);b.setFont(b.getFont().deriveFont(b.getFont().getSize2D()*scale));return b;}
  private static void visibleButton(JButton button,JComponent outer,String label){
    Rectangle bounds=SwingUtilities.convertRectangle(button.getParent(),button.getBounds(),outer),clip=new Rectangle(0,0,outer.getWidth(),outer.getHeight());Component c=button;
    while(c!=outer&&c.getParent()!=null){Container p=c.getParent();clip=clip.intersection(SwingUtilities.convertRectangle(p,new Rectangle(0,0,p.getWidth(),p.getHeight()),outer));c=p;}
    check(clip.contains(bounds),label+" clipped "+button.getText()+": "+bounds+" clip="+clip);check(bounds.width>=button.getPreferredSize().width,label+" button text clipped");
  }
  private static void hierarchy(int width,float scale,boolean longName){
    JPanel outer=new JPanel(new BorderLayout(0,6));outer.setBorder(BorderFactory.createEmptyBorder(6,6,6,6));outer.setSize(width,600);
    JComboBox<String> profiles=new JComboBox<>(new String[]{longName?"资料库 profile ".repeat(80):"short"});profiles.setFont(profiles.getFont().deriveFont(profiles.getFont().getSize2D()*scale));
    JButton[] connection=Arrays.stream(new String[]{"+","Edit","Remove","Connect","Disconnect"}).map(s->button(s,scale)).toArray(JButton[]::new);
    JPanel top=new JPanel(new BorderLayout(0,3));top.add(profiles,BorderLayout.NORTH);top.add(DatabaseToolbarLayout.row(connection),BorderLayout.CENTER);outer.add(top,BorderLayout.NORTH);
    JPanel sql=new JPanel();sql.setPreferredSize(new Dimension(700,200));
    JButton[] commands=Arrays.stream(new String[]{"Run statement","Cancel","Begin transaction","Commit","Rollback"}).map(s->button(s,scale)).toArray(JButton[]::new);
    JPanel actions=DatabaseToolbarLayout.row(commands),editor=new JPanel(new BorderLayout(0,4));editor.add(sql,BorderLayout.CENTER);editor.add(actions,BorderLayout.NORTH);
    JPanel browser=new JPanel(new BorderLayout(0,4));browser.add(new JScrollPane(new JList<>()),BorderLayout.CENTER);JPanel browseActions=new JPanel(new GridLayout(0,1,2,2));JButton[] browse=Arrays.stream(new String[]{"Refresh tables","Columns","Select rows"}).map(s->button(s,scale)).toArray(JButton[]::new);for(JButton b:browse)browseActions.add(b);browser.add(browseActions,BorderLayout.SOUTH);browser.setPreferredSize(new Dimension(140,400));
    DatabaseContentLayout content=new DatabaseContentLayout(browser,editor,actions,sql,new JScrollPane(new JTable()),browseActions);outer.add(content,BorderLayout.CENTER);outer.add(new JLabel("Database status"),BorderLayout.SOUTH);
    for(int i=0;i<12;i++)layout(outer);String label=width+"px scale="+scale+" long="+longName;
    for(JButton b:connection)visibleButton(b,outer,label);for(JButton b:commands)visibleButton(b,outer,label);
    content.querySplit().setDividerLocation(content.querySplit().getUI().getMinimumDividerLocation(content.querySplit()));for(int i=0;i<6;i++)layout(outer);for(JButton b:commands)visibleButton(b,outer,label+" minimum divider");
    if(!content.isTabbed()){content.browserSplit().setDividerLocation(content.browserSplit().getUI().getMaximumDividerLocation(content.browserSplit()));for(int i=0;i<6;i++)layout(outer);for(JButton b:commands)visibleButton(b,outer,label+" maximum browser divider");}
    if(content.isTabbed()){content.tabs().setSelectedIndex(0);for(int i=0;i<6;i++)layout(outer);}for(JButton b:browse)visibleButton(b,outer,label+" tables");
  }
  public static void main(String[] args)throws Exception{
    SwingUtilities.invokeAndWait(()->{
      for(int width:new int[]{320,450,700}){
        row(width,"+","Edit","Remove","Connect","Disconnect");
        row(width,"Run statement","Cancel","Begin transaction","Commit","Rollback");
      }
      // At a 450px default tool window, a 140px browser leaves a 290px editor.
      row(290,"Run statement","Cancel","Begin transaction","Commit","Rollback");
      JPanel outer=new JPanel(new BorderLayout());outer.setSize(450,300);JComboBox<String> profiles=new JComboBox<>(new String[]{"Profile name that is intentionally wider than the panel ".repeat(5)});JPanel top=new JPanel(new BorderLayout());top.add(profiles,BorderLayout.NORTH);JPanel buttons=DatabaseToolbarLayout.row(new JButton("Connect"),new JButton("Disconnect"));top.add(buttons,BorderLayout.CENTER);outer.add(top,BorderLayout.NORTH);outer.doLayout();top.doLayout();buttons.doLayout();check(profiles.getWidth()==450&&buttons.getWidth()==450,"profile width cannot push connection actions outside panel");for(Component button:buttons.getComponents())check(button.getY()+button.getHeight()<=buttons.getHeight(),"connection action within allocated height");
      for(float scale:new float[]{1,1.25f,1.5f,2})for(int width:new int[]{300,320,450,700})for(boolean longName:new boolean[]{false,true})hierarchy(width,scale,longName);
    });
    System.out.println("{\"status\":\"pass\",\"checks\":"+checks+",\"offscreenOnly\":true,\"widths\":[290,300,320,450,700],\"fontMetricScales\":[1,1.25,1.5,2],\"fullHierarchyAndMinimumDividerTested\":true,\"narrowTabsTested\":true,\"nativeIdeLaunched\":false}");
  }
}
