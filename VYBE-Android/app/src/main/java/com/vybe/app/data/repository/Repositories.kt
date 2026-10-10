package com.vybe.app.data.repository

import com.vybe.app.data.api.ApiError
import com.vybe.app.data.api.SettingsStore
import com.vybe.app.data.api.VybeApi
import com.vybe.app.data.api.ioCall
import com.vybe.app.data.models.Booking
import com.vybe.app.data.models.ChatMessage
import com.vybe.app.data.models.Conversation
import com.vybe.app.data.models.Enquiry
import com.vybe.app.data.models.Interest
import com.vybe.app.data.models.LoginBody
import com.vybe.app.data.models.MessageBody
import com.vybe.app.data.models.RegisterBody
import com.vybe.app.data.models.SwipeBody
import com.vybe.app.data.models.TravelPackage
import com.vybe.app.data.models.TravelerProfile
import com.vybe.app.data.models.User

/** Auth + identity state. Server is the source of truth; client never trusts stored role. */
class SessionRepository(
    private val settings: SettingsStore,
    private val apiOf: suspend () -> VybeApi
) {
    private val _user = kotlinx.coroutines.flow.MutableStateFlow<User?>(null)
    val user: kotlinx.coroutines.flow.StateFlow<User?> = _user

    suspend fun login(email: String, password: String): User {
        val u = ioCall { apiOf().login(LoginBody(email.trim(), password)) }.user
        if (u.status != "active") throw ApiError(403, "Account suspended")
        _user.value = u
        settings.cacheIdentity(u.name, u.role)
        return u
    }

    suspend fun register(name: String, email: String, password: String, role: String): User {
        val u = ioCall {
            apiOf().register(RegisterBody(name.trim(), email.trim(), password, role))
        }.user
        _user.value = u
        settings.cacheIdentity(u.name, u.role)
        return u
    }

    suspend fun logout() {
        try {
            ioCall { apiOf().logout() }
        } catch (e: Exception) {
            // server already gone / session expired: still clear locally
        }
        _user.value = null
        settings.clearIdentity()
    }

    suspend fun refresh(): User? {
        val me = try {
            ioCall { apiOf().getProfile() }.user
        } catch (e: ApiError) {
            if (e.status == 401 || e.status == 403) {
                _user.value = null
                return null
            }
            throw e
        }
        _user.value = me
        return me
    }
}

/** Packages, discovery, interests — thin pass-through; rules live on the server. */
class TravelRepository(private val apiOf: suspend () -> VybeApi) {
    suspend fun packages(): List<TravelPackage> = ioCall { apiOf().packages() }.packages
    suspend fun detail(id: Int): TravelPackage = ioCall { apiOf().packageDetail(id) }.pkg
    suspend fun recommended(): Pair<List<TravelPackage>, TravelerProfile?> {
        val r = ioCall { apiOf().recommended() }
        return r.packages to r.prefs
    }
    suspend fun swipe(id: Int, action: String) {
        ioCall { apiOf().swipe(id, SwipeBody(action)) }
    }
    suspend fun like(id: Int, on: Boolean) {
        if (on) ioCall { apiOf().like(id) } else ioCall { apiOf().unlike(id) }
    }
    suspend fun save(id: Int, on: Boolean) {
        if (on) ioCall { apiOf().save(id) } else ioCall { apiOf().unsave(id) }
    }
    suspend fun interests(action: String? = null): List<Interest> =
        ioCall { apiOf().interests(action) }.interests

    suspend fun profile(): Pair<User, TravelerProfile> {
        val r = ioCall { apiOf().getProfile() }
        return r.user to r.profile
    }

    suspend fun updateProfile(fields: Map<String, Any?>): Pair<User, TravelerProfile> {
        val r = ioCall { apiOf().updateProfile(fields) }
        return r.user to r.profile
    }
}

/** My Trips: enquiries + bookings, straight from the server (no invented states). */
class TripsRepository(private val apiOf: suspend () -> VybeApi) {
    suspend fun enquiries(): List<Enquiry> = ioCall { apiOf().enquiries() }.enquiries
    suspend fun bookings(): List<Booking> = ioCall { apiOf().bookings() }.bookings
}

/** Chats: polling-friendly list + messages (matches web polling strategy). */
class ChatRepository(private val apiOf: suspend () -> VybeApi) {
    suspend fun conversations(): List<Conversation> =
        ioCall { apiOf().conversations() }.conversations

    suspend fun messages(conversationId: Int): List<ChatMessage> =
        ioCall { apiOf().messages(conversationId) }.messages

    suspend fun send(conversationId: Int, body: String): ChatMessage =
        ioCall { apiOf().sendMessage(conversationId, MessageBody(body)) }.message
}
