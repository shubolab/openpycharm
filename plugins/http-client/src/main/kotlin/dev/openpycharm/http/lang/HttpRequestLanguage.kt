// Adapted with author authorization from shubolab/opengoland, commit 3b32dc53df49388528203fa9b600b93ea69b8368.
// Original source path: src/main/kotlin/dev/openidea/goide/lang/HttpRequestLanguage.kt
package dev.openpycharm.http.lang

import com.intellij.icons.AllIcons
import com.intellij.lang.Commenter
import com.intellij.lang.Language
import com.intellij.openapi.fileTypes.LanguageFileType

object HttpRequestLanguage : Language("OpenPyCharmHttpRequest") {
    override fun getDisplayName() = "HTTP Request"
}

class HttpRequestFileType private constructor() : LanguageFileType(HttpRequestLanguage) {
    override fun getName() = "OpenPyCharm HTTP Request"
    override fun getDescription() = "HTTP request document"
    override fun getDefaultExtension() = "http"
    override fun getIcon() = AllIcons.FileTypes.Text

    companion object {
        @JvmField val INSTANCE = HttpRequestFileType()
    }
}

class HttpRequestCommenter : Commenter {
    override fun getLineCommentPrefix() = "#"
    override fun getBlockCommentPrefix(): String? = null
    override fun getBlockCommentSuffix(): String? = null
    override fun getCommentedBlockCommentPrefix(): String? = null
    override fun getCommentedBlockCommentSuffix(): String? = null
}
