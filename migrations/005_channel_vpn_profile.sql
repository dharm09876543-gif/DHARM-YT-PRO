-- Phase 9: optional WireGuard profile per channel (e.g. 'ch01'). The config itself lives only in the
-- WG_CONF_<PROFILE> secret / env var, never in the database or the repo. NULL = no VPN for this channel.
ALTER TABLE channels ADD COLUMN vpn_profile TEXT;
