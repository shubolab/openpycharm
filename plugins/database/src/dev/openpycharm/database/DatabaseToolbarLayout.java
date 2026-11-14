package dev.openpycharm.database;

import java.awt.*;
import java.awt.event.ComponentAdapter;
import java.awt.event.ComponentEvent;
import javax.swing.*;

/** Native Swing rows report their wrapped height to BorderLayout/JSplitPane. */
public final class DatabaseToolbarLayout extends FlowLayout {
  public DatabaseToolbarLayout(){super(FlowLayout.LEFT,4,3);}
  public static JPanel row(JComponent... components){
    JPanel panel=new JPanel(new DatabaseToolbarLayout());for(JComponent c:components)panel.add(c);
    panel.addComponentListener(new ComponentAdapter(){@Override public void componentResized(ComponentEvent e){panel.revalidate();}});
    return panel;
  }
  @Override public Dimension preferredLayoutSize(Container target){return measured(target,false);}
  @Override public Dimension minimumLayoutSize(Container target){return measured(target,true);}
  private Dimension measured(Container target,boolean minimum){
    synchronized(target.getTreeLock()){
      int width=target.getWidth();Container parent=target.getParent();
      while(width<=0&&parent!=null){width=parent.getWidth();parent=parent.getParent();}
      if(width<=0)width=Integer.MAX_VALUE;
      Insets insets=target.getInsets();int available=Math.max(1,width-insets.left-insets.right-getHgap()*2);
      int rowWidth=0,rowHeight=0,totalHeight=0,maxWidth=0;
      for(Component c:target.getComponents())if(c.isVisible()){
        Dimension d=minimum?c.getMinimumSize():c.getPreferredSize();
        int next=rowWidth==0?d.width:rowWidth+getHgap()+d.width;
        if(rowWidth>0&&next>available){maxWidth=Math.max(maxWidth,rowWidth);totalHeight+=rowHeight+getVgap();rowWidth=d.width;rowHeight=d.height;}
        else {rowWidth=next;rowHeight=Math.max(rowHeight,d.height);}
      }
      maxWidth=Math.max(maxWidth,rowWidth);totalHeight+=rowHeight;
      return new Dimension(maxWidth+insets.left+insets.right+getHgap()*2,totalHeight+insets.top+insets.bottom+getVgap()*2);
    }
  }
}
