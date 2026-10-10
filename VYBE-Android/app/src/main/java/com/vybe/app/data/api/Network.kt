package com.vybe.app.data.api

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.google.gson.GsonBuilder
import java.net.CookieManager
import java.net.CookiePolicy
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import okhttp3.JavaNetCookieJar
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

private val Context.settingsStore: DataStore<Preferences> by preferencesDataStore("vybe_settings")

/**
 * Non-sensitive settings only (server URL, cached display name/role).
 * Auth lives in the OkHttp cookie jar (memory) + server session:
 * nothing secret is persisted. Restart/expiry -> re-login screen.
 */
class SettingsStore(private val context: Context) {
    private val baseUrl = stringPreferencesKey("api_base_url")
    private val cachedName = stringPreferencesKey("cached_name")
    private val cachedRole = stringPreferencesKey("cached_role")

    /** Emulator -> host loopback. Physical phone -> laptop LAN IP. ngrok URL also works. */
    val defaultBaseUrl = "http://10.0.2.2:5000/"

    fun baseUrlFlow(): Flow<String> =
        context.settingsStore.data.map { it[baseUrl] ?: defaultBaseUrl }

    suspend fun setBaseUrl(url: String) {
        val clean = url.trim().trimEnd('/') + "/"
        context.settingsStore.edit { it[baseUrl] = clean }
    }

    suspend fun cacheIdentity(name: String, role: String) {
        context.settingsStore.edit { it[cachedName] = name; it[cachedRole] = role }
    }

    suspend fun clearIdentity() {
        context.settingsStore.edit { it.remove(cachedName); it.remove(cachedRole) }
    }
}

object Network {
    /** In-memory cookie jar: session cookie survives while the app runs. */
    fun newClient(debug: Boolean): OkHttpClient {
        val jar = JavaNetCookieJar(CookieManager(null, CookiePolicy.ACCEPT_ALL))
        val builder = OkHttpClient.Builder()
            .cookieJar(jar)
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
        if (debug) {
            builder.addInterceptor(HttpLoggingInterceptor().setLevel(HttpLoggingInterceptor.Level.BASIC))
        }
        return builder.build()
    }

    fun newApi(baseUrl: String, client: OkHttpClient): VybeApi {
        val url = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
        return Retrofit.Builder()
            .baseUrl(url)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create(GsonBuilder().create()))
            .build()
            .create(VybeApi::class.java)
    }
}

/** Thrown for transport-level failures so UI can show offline states. */
class NetworkError(message: String, cause: Throwable? = null) : Exception(message, cause)

/** Thrown for HTTP errors; carries status + optional server message. */
class ApiError(val status: Int, message: String) : Exception(message)

suspend fun <T> ioCall(block: suspend () -> retrofit2.Response<T>): T {
    val res = try {
        block()
    } catch (e: Exception) {
        throw NetworkError("No connection to the VYBE server", e)
    }
    if (!res.isSuccessful) {
        val msg = try {
            res.errorBody()?.string()?.take(200)
        } catch (e: Exception) {
            null
        }
        throw ApiError(res.code(), msg ?: "Server error ${res.code()}")
    }
    return res.body() ?: throw ApiError(res.code(), "Empty response")
}
