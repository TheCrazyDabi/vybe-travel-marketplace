package com.vybe.app

import android.app.Application
import com.vybe.app.data.api.Network
import com.vybe.app.data.api.SettingsStore
import com.vybe.app.data.api.VybeApi
import com.vybe.app.data.repository.SessionRepository
import com.vybe.app.data.repository.TravelRepository

/** Manual service locator: one OkHttp client (cookie session), Retrofit per base URL. */
class VybeApp : Application() {
    lateinit var settings: SettingsStore
        private set

    private val http by lazy { Network.newClient(BuildConfig.DEBUG) }
    private var cachedUrl: String? = null
    private var cachedApi: VybeApi? = null

    val session: SessionRepository by lazy {
        SessionRepository(settings) { api() }
    }
    val travel: TravelRepository by lazy {
        TravelRepository { api() }
    }

    override fun onCreate() {
        super.onCreate()
        settings = SettingsStore(applicationContext)
    }

    /** Rebuilds Retrofit only when the configured base URL changed. */
    suspend fun api(): VybeApi {
        val url = kotlinx.coroutines.flow.first(settings.baseUrlFlow())
        return apiFor(url)
    }

    fun apiFor(url: String): VybeApi {
        if (cachedApi == null || cachedUrl != url) {
            cachedApi = Network.newApi(url, http)
            cachedUrl = url
        }
        return cachedApi!!
    }
}
