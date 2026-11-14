package dev.openpycharm.database;

import com.intellij.codeInsight.completion.*;
import com.intellij.codeInsight.lookup.AutoCompletionPolicy;
import com.intellij.codeInsight.lookup.LookupElementBuilder;
import com.intellij.codeInsight.lookup.LookupElement;
import com.intellij.codeInsight.lookup.LookupElementDecorator;
import com.intellij.codeInsight.lookup.LookupElementInsertStopper;
import com.intellij.openapi.editor.Editor;
import com.intellij.openapi.project.DumbAware;
import java.util.ArrayList;
import java.util.List;
import org.jetbrains.annotations.NotNull;

/** Native completion consumes only an already-created service's immutable snapshot. */
public final class SqlCompletionContributor extends CompletionContributor implements DumbAware {
  @Override public void beforeCompletion(@NotNull CompletionInitializationContext context){
    if(context.getCompletionType()!=CompletionType.BASIC)return;
    DatabaseService service=DatabaseService.created(context.getProject());if(service==null||service.completionSnapshot()==null)return;
    var document=context.getEditor().getDocument();if(document.getTextLength()>SqlCompletionContext.MAX_TEXT)return;
    var parsed=SqlCompletionContext.analyze(document.getText(),context.getEditor().getCaretModel().getOffset());
    if(parsed.mode()==SqlCompletionContext.Mode.NONE)return;
    // START_OFFSET is the caret used to build CompletionParameters, not the identifier start.
    // Native Lookup derives replacement start from the matcher's raw prefix length.
    context.getOffsetMap().addOffset(CompletionInitializationContext.IDENTIFIER_END_OFFSET,parsed.replaceEnd());
  }
  @Override public void fillCompletionVariants(@NotNull CompletionParameters parameters,@NotNull CompletionResultSet result){
    if(parameters.getCompletionType()!=CompletionType.BASIC)return;
    var project=parameters.getOriginalFile().getProject();if(project.isDisposed())return;
    // Project user data only: even getServiceIfCreated has an initializing default in this SDK.
    DatabaseService service=DatabaseService.created(project);if(service==null)return;
    DatabaseMetadataCache.Snapshot snapshot=service.completionSnapshot();if(snapshot==null)return;
    var document=parameters.getEditor().getDocument();if(document.getTextLength()>SqlCompletionContext.MAX_TEXT)return;
    if(parameters.getEditor().getCaretModel().getCaretCount()!=1)return;
    String text=document.getText();var context=SqlCompletionContext.analyze(text,parameters.getOffset());
    if(context.mode()==SqlCompletionContext.Mode.NONE)return;
    var matching=result.withPrefixMatcher(new SqlCompletionPrefixMatcher(context.rawPrefix()));
    List<LookupElement> prepared=new ArrayList<>();
    for(var candidate:SqlCompletionCandidates.suggest(snapshot,context)){
      if(service.completionSnapshot()!=snapshot)return;
      prepared.add(lookup(service,snapshot,candidate,parameters.getEditor()));
    }
    if(service.completionSnapshot()==snapshot)matching.addAllElements(prepared);
  }
  static LookupElement lookup(DatabaseService service,DatabaseMetadataCache.Snapshot snapshot,SqlCompletionCandidates.Candidate candidate,Editor editor){
    var presentation=LookupElementBuilder.create(candidate.name()).withCaseSensitivity(false)
      .withTypeText(candidate.kind()).withTailText(candidate.detail().isEmpty()?"":"  "+candidate.detail(),true)
      .withAutoCompletionPolicy(AutoCompletionPolicy.NEVER_AUTOCOMPLETE);
    return new SnapshotLookup(presentation,service,snapshot,candidate,editor);
  }
  private static final class SnapshotLookup extends LookupElementDecorator<LookupElement> implements LookupElementInsertStopper {
    private final DatabaseService service;private final DatabaseMetadataCache.Snapshot snapshot;
    private final SqlCompletionCandidates.Candidate candidate;private final Editor editor;
    private String acceptedText;private int acceptedCaret;
    SnapshotLookup(LookupElement delegate,DatabaseService service,DatabaseMetadataCache.Snapshot snapshot,SqlCompletionCandidates.Candidate candidate,Editor editor){
      super(delegate);this.service=service;this.snapshot=snapshot;this.candidate=candidate;this.editor=editor;
    }
    @Override public boolean isValid(){return super.isValid()&&service.completionSnapshot()==snapshot&&editor.getDocument().getTextLength()<=SqlCompletionContext.MAX_TEXT&&editor.getCaretModel().getCaretCount()==1;}
    @Override public boolean shouldStopLookupInsertion(){
      // Pinned LookupImpl calls this immediately before its default word insertion.
      // Capture the current text, including additional typing and the identifier suffix.
      var document=editor.getDocument();if(document.getTextLength()>SqlCompletionContext.MAX_TEXT)return true;
      acceptedText=document.getText();acceptedCaret=editor.getCaretModel().getOffset();return false;
    }
    @Override public void handleInsert(@NotNull InsertionContext insertion){
      insertion.setAddCompletionChar(false);
      String accepted=acceptedText;acceptedText=null;if(accepted==null)return;
      if(service.completionSnapshot()!=snapshot){restore(insertion,accepted,acceptedCaret);return;}
      int start=insertion.getStartOffset(),end=Math.max(insertion.getTailOffset(),insertion.getOffset(CompletionInitializationContext.IDENTIFIER_END_OFFSET));
      if(start<0||end<start||end>insertion.getDocument().getTextLength()){restore(insertion,accepted,acceptedCaret);return;}
      insertion.getDocument().replaceString(start,end,candidate.insertion());
      insertion.setTailOffset(start+candidate.insertion().length());insertion.getEditor().getCaretModel().moveToOffset(insertion.getTailOffset());
      if(service.completionSnapshot()!=snapshot)restore(insertion,accepted,acceptedCaret);
    }
    private static void restore(InsertionContext insertion,String accepted,int acceptedCaret){
      // Restore only the changed span so untouched text/range markers remain intact.
      var document=insertion.getDocument();String current=document.getText();int start=0;
      while(start<current.length()&&start<accepted.length()&&current.charAt(start)==accepted.charAt(start))start++;
      int currentEnd=current.length(),acceptedEnd=accepted.length();
      while(currentEnd>start&&acceptedEnd>start&&current.charAt(currentEnd-1)==accepted.charAt(acceptedEnd-1)){currentEnd--;acceptedEnd--;}
      document.replaceString(start,currentEnd,accepted.substring(start,acceptedEnd));
      insertion.setTailOffset(acceptedCaret);insertion.getEditor().getCaretModel().moveToOffset(acceptedCaret);
    }
  }
}
