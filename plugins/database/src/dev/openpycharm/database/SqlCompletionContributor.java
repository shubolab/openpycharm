package dev.openpycharm.database;

import com.intellij.codeInsight.completion.*;
import com.intellij.codeInsight.lookup.AutoCompletionPolicy;
import com.intellij.codeInsight.lookup.LookupElementBuilder;
import com.intellij.codeInsight.lookup.LookupElement;
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
    context.getOffsetMap().addOffset(CompletionInitializationContext.START_OFFSET,parsed.replaceStart());
    context.getOffsetMap().addOffset(CompletionInitializationContext.IDENTIFIER_END_OFFSET,parsed.replaceEnd());
  }
  @Override public void fillCompletionVariants(@NotNull CompletionParameters parameters,@NotNull CompletionResultSet result){
    if(parameters.getCompletionType()!=CompletionType.BASIC)return;
    var project=parameters.getOriginalFile().getProject();if(project.isDisposed())return;
    // Project user data only: even getServiceIfCreated has an initializing default in this SDK.
    DatabaseService service=DatabaseService.created(project);if(service==null)return;
    DatabaseMetadataCache.Snapshot snapshot=service.completionSnapshot();if(snapshot==null)return;
    var document=parameters.getEditor().getDocument();if(document.getTextLength()>SqlCompletionContext.MAX_TEXT)return;
    String text=document.getText();var context=SqlCompletionContext.analyze(text,parameters.getOffset());
    if(context.mode()==SqlCompletionContext.Mode.NONE)return;
    String original=text.substring(context.replaceStart(),context.replaceEnd());
    var matching=result.withPrefixMatcher(new PlainPrefixMatcher(context.prefix(),true)).caseInsensitive();
    List<LookupElement> prepared=new ArrayList<>();
    for(var candidate:SqlCompletionCandidates.suggest(snapshot,context)){
      if(service.completionSnapshot()!=snapshot)return;
      var lookup=LookupElementBuilder.create(candidate.name()).withCaseSensitivity(false)
        .withTypeText(candidate.kind()).withTailText(candidate.detail().isEmpty()?"":"  "+candidate.detail(),true)
        .withInsertHandler((insertion,item)->{
          int start=insertion.getStartOffset();int end=Math.max(insertion.getTailOffset(),insertion.getOffset(CompletionInitializationContext.IDENTIFIER_END_OFFSET));
          String replacement=service.completionSnapshot()==snapshot?candidate.insertion():original;
          if(start<0||end<start||end>insertion.getDocument().getTextLength())return;
          insertion.getDocument().replaceString(start,end,replacement);
          insertion.setTailOffset(start+replacement.length());insertion.getEditor().getCaretModel().moveToOffset(start+replacement.length());insertion.setAddCompletionChar(false);
        }).withAutoCompletionPolicy(AutoCompletionPolicy.NEVER_AUTOCOMPLETE);
      prepared.add(lookup);
    }
    if(service.completionSnapshot()==snapshot)matching.addAllElements(prepared);
  }
}
