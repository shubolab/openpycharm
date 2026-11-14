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
  public static void main(String[] args)throws Exception{
    SwingUtilities.invokeAndWait(()->{
      for(int width:new int[]{320,450,700}){
        row(width,"+","Edit","Remove","Connect","Disconnect");
        row(width,"Run statement","Cancel","Begin transaction","Commit","Rollback");
      }
      // At a 450px default tool window, a 140px browser leaves a 290px editor.
      row(290,"Run statement","Cancel","Begin transaction","Commit","Rollback");
      JPanel outer=new JPanel(new BorderLayout());outer.setSize(450,300);JComboBox<String> profiles=new JComboBox<>(new String[]{"Profile name that is intentionally wider than the panel ".repeat(5)});JPanel top=new JPanel(new BorderLayout());top.add(profiles,BorderLayout.NORTH);JPanel buttons=DatabaseToolbarLayout.row(new JButton("Connect"),new JButton("Disconnect"));top.add(buttons,BorderLayout.CENTER);outer.add(top,BorderLayout.NORTH);outer.doLayout();top.doLayout();buttons.doLayout();check(profiles.getWidth()==450&&buttons.getWidth()==450,"profile width cannot push connection actions outside panel");for(Component button:buttons.getComponents())check(button.getY()+button.getHeight()<=buttons.getHeight(),"connection action within allocated height");
    });
    System.out.println("{\"status\":\"pass\",\"checks\":"+checks+",\"offscreenOnly\":true,\"widths\":[290,320,450,700],\"nativeIdeLaunched\":false}");
  }
}
