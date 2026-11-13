package dev.openpycharm.http

import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import java.io.IOException
import java.net.InetSocketAddress
import java.time.Duration
import java.util.concurrent.CompletableFuture
import java.util.concurrent.CountDownLatch
import java.util.concurrent.ExecutionException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/** Loopback-only integration checks of the same parser/transport used by the native plugin. */
private class Fixture : AutoCloseable {
    val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
    private val executor = Executors.newCachedThreadPool()
    val base get() = "http://127.0.0.1:${server.address.port}"
    var closed = false
        private set
    init { server.executor = executor; server.start() }
    fun route(path: String, handler: (HttpExchange) -> Unit) {
        server.createContext(path) { exchange ->
            try { handler(exchange) }
            catch (_: IOException) { /* Expected after real socket cancellation. */ }
            catch (_: InterruptedException) { Thread.currentThread().interrupt() }
            finally { exchange.close() }
        }
    }
    override fun close() {
        server.stop(0)
        executor.shutdownNow()
        check(executor.awaitTermination(5, TimeUnit.SECONDS)) { "Owned HTTP server workers did not stop" }
        closed = true
    }
}

private inline fun rejected(block: () -> Unit) {
    try { block() } catch (_: IllegalArgumentException) { return }
    error("Expected unsupported/malformed request to be rejected")
}

fun main() {
    val checks = mutableListOf<String>()
    val fixture = Fixture()
    fixture.use {
        val captured = AtomicReference<String>()
        fixture.route("/echo") { exchange ->
            val body = exchange.requestBody.readAllBytes()
            captured.set("${exchange.requestMethod}|${exchange.requestHeaders.getFirst("X-Probe")}|${String(body, Charsets.UTF_8)}")
            val response = "{\"message\":\"你好😀\"}".toByteArray(Charsets.UTF_8)
            exchange.responseHeaders.add("Content-Type", "application/json; charset=UTF-8")
            exchange.responseHeaders.add("X-Answer", "preserved")
            exchange.sendResponseHeaders(422, response.size.toLong())
            exchange.responseBody.write(response)
        }
        val request = HttpRequestDocument.requestAt("POST ${fixture.base}/echo\r\nX-Probe: native\r\nContent-Type: application/json\r\n\r\n 你好😀 \r\n\r\n", 0)
        val response = HttpRequestCall(request).use { it.await() }
        check(captured.get() == "POST|native| 你好😀 ")
        check(response.status == 422 && response.displayBody() == "{\"message\":\"你好😀\"}")
        check(response.headers["x-answer"] == listOf("preserved"))
        checks += "real UTF-8 POST preserves body whitespace, request/response headers and HTTP error status"

        val raw = byteArrayOf(0, -1, -128, 1, 2)
        fixture.route("/binary") { exchange ->
            exchange.responseHeaders.add("Content-Type", "application/octet-stream")
            exchange.sendResponseHeaders(200, raw.size.toLong()); exchange.responseBody.write(raw)
        }
        val binary = HttpRequestCall(HttpRequestDocument.requestAt("GET ${fixture.base}/binary", 0)).use { it.await() }
        check(binary.body.contentEquals(raw))
        check(binary.displayBody().startsWith("[Binary response:"))
        checks += "raw response bytes are preserved and binary data is not rendered as text"

        val redirected = AtomicInteger()
        fixture.route("/redirect") { exchange ->
            exchange.responseHeaders.add("Location", "${fixture.base}/redirect-target")
            exchange.responseHeaders.add("Set-Cookie", "session=not-retained")
            exchange.sendResponseHeaders(302, -1)
        }
        fixture.route("/redirect-target") { exchange -> redirected.incrementAndGet(); exchange.sendResponseHeaders(204, -1) }
        val cookie = AtomicReference<String?>()
        fixture.route("/cookie") { exchange -> cookie.set(exchange.requestHeaders.getFirst("Cookie")); exchange.sendResponseHeaders(204, -1) }
        check(HttpRequestCall(HttpRequestDocument.requestAt("GET ${fixture.base}/redirect", 0)).use { it.await() }.status == 302)
        HttpRequestCall(HttpRequestDocument.requestAt("GET ${fixture.base}/cookie", 0)).use { it.await() }
        check(redirected.get() == 0 && cookie.get() == null)
        checks += "redirect responses are visible and requests do not acquire a shared cookie jar"

        fixture.route("/large") { exchange -> exchange.sendResponseHeaders(200, 0); exchange.responseBody.write(ByteArray(8192)) }
        val bounded = HttpRequestCall(HttpRequestDocument.requestAt("GET ${fixture.base}/large", 0), maxResponseBytes = 128)
        try { bounded.use { it.await() }; error("Oversized chunked response was accepted") }
        catch (failure: ExecutionException) { check(failure.cause?.message?.contains("128-byte limit") == true) }
        checks += "streaming response limit applies without Content-Length"

        val received = CountDownLatch(1)
        val disconnected = CountDownLatch(1)
        fixture.route("/stream") { exchange ->
            exchange.sendResponseHeaders(200, 0)
            try {
                repeat(1000) {
                    exchange.responseBody.write(ByteArray(1024)); exchange.responseBody.flush()
                    received.countDown(); Thread.sleep(10)
                }
            } catch (_: IOException) { disconnected.countDown() }
        }
        val streaming = HttpRequestCall(HttpRequestDocument.requestAt("GET ${fixture.base}/stream", 0))
        val pending = CompletableFuture.supplyAsync { streaming.await() }
        try {
            check(received.await(5, TimeUnit.SECONDS))
            streaming.close()
            try { pending.get(3, TimeUnit.SECONDS); error("Cancelled HTTP call completed normally") }
            catch (_: ExecutionException) { }
            check(disconnected.await(5, TimeUnit.SECONDS)) { "Cancellation did not close the real socket" }
        } finally { streaming.close() }
        checks += "cancel completes the pending call and disconnects the active streaming socket"

        val headersSent = CountDownLatch(1)
        val release = CountDownLatch(1)
        fixture.route("/stall") { exchange ->
            exchange.sendResponseHeaders(200, 0); exchange.responseBody.write(1); exchange.responseBody.flush()
            headersSent.countDown(); release.await(5, TimeUnit.SECONDS)
        }
        val stalled = HttpRequestCall(HttpRequestDocument.requestAt("GET ${fixture.base}/stall", 0), Duration.ofMillis(500))
        try {
            check(headersSent.await(3, TimeUnit.SECONDS))
            try { stalled.use { it.await() }; error("Stalled body did not time out") }
            catch (_: TimeoutException) { }
        } finally { release.countDown(); stalled.close() }
        checks += "deadline includes a response body stalled after headers"

        val order = mutableListOf<String>()
        fixture.route("/ordered") { exchange -> synchronized(order) { order += exchange.requestHeaders.getFirst("X-Order") }; exchange.sendResponseHeaders(204, -1) }
        val document = "@base = ${fixture.base}\n### First\nGET {{base}}/ordered\nX-Order: first\n\n### Second\n# @name second\nPOST {{base}}/ordered\nX-Order: second\n\nbody"
        val plan = HttpRequestDocument.plan(document)
        check(plan.entries.size == 2 && plan.entries[1].displayName == "second")
        for (entry in plan.entries) HttpRequestCall(plan.parse(entry)).use { check(it.await().status == 204) }
        check(order == listOf("first", "second"))
        check(plan.entryAt(document.indexOf("### Second")) === plan.entries[1])
        checks += "file variables, named requests, caret selection and ordered plan requests reach the server"

        rejected { HttpRequestDocument.requestAt("GET http://user:password@localhost/", 0) }
        rejected { HttpRequestDocument.requestAt("GET ${fixture.base}/\nHost: overridden", 0) }
        rejected { HttpRequestDocument.requestAt("@a = {{b}}\n@b = {{a}}\nGET {{a}}", 0) }
        rejected { HttpRequestDocument.requestAt("GET {{missing}}/", 0) }
        rejected { HttpRequestDocument.requestAt("POST ${fixture.base}/\n\n< ./payload.json", 0) }
        rejected { HttpRequestDocument.requestAt("POST ${fixture.base}/\n\n" + "x".repeat(1024 * 1024 + 1), 0) }
        checks += "unsupported credentials, managed headers, variable cycles, missing variables, file bodies and oversized request bodies fail explicitly"
    }
    check(fixture.closed)
    println("{\"status\":\"pass\",\"serverOwnedClosed\":true,\"checkCount\":${checks.size},\"checks\":[" +
        checks.joinToString(",") { "\"$it\"" } + "]}")
}
