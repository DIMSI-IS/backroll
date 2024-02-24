echo "Starting BackROLL configuration…"

key_file=backroll-dev/ssh/id
if ! test -f "$key_file"; then
    echo "Generating ssh key…"
    ssh-keygen -t ed25519 -N "" -f "$key_file" -C "BackROLL" -q
    echo "…done."
fi

echo "Copying ssh directory…"
for container in api worker_primary worker_secondary; do
    mkdir -p backroll-dev/$container/ssh
    cp backroll-dev/ssh/* backroll-dev/$container/ssh/
done
echo "…done."

echo "BackROLL configuration is done."
