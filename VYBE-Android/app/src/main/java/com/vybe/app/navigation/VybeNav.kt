package com.vybe.app.navigation

/** Single source of truth for destinations. Bottom bar: Discover, Explore, Trips, Chats, Saved. */
object Destinations {
    const val SPLASH = "splash"
    const val LOGIN = "login"
    const val REGISTER = "register"
    const val SERVER = "server"
    const val DISCOVER = "discover"
    const val EXPLORE = "explore"
    const val DETAIL = "detail/{packageId}"
    const val SAVED = "saved"
    const val PREFS = "prefs"
    const val TRIPS = "trips"
    const val CHATS = "chats"
    const val CHAT_DETAIL = "chat/{conversationId}"
    const val PROFILE = "profile"

    fun detail(id: Int) = "detail/$id"
    fun chat(id: Int) = "chat/$id"
}
