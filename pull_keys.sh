#!/bin/bash

BASE_DIR="/home/miniint/mini-internet"

mkdir -p keys/master
mkdir -p keys/ases

# Pull master keys
echo "Pulling master keys..."
cp $BASE_DIR/platform/groups/id_rsa* ./keys/master/
chmod 600 ./keys/master/id_rsa*

# Loop for each ASN that conforms to the template "{'' or 1-6}{3-6}" and ASN <= 63
for i in "" {1..6}; do
    for j in {3..6}; do
        ASN_VAL="${i}${j}"

        # Ensure the ASN is within the requested range (<= 63)
        if [ "$ASN_VAL" -le 63 ]; then
            # Zero-pad ASN for directory names and namespace (e.g., 03)
            ASN=$(printf "%02d" $ASN_VAL)
            PORT=$((2000 + ASN_VAL))

            echo "Processing ASN $ASN (Port $PORT)..."

            # 1. Create directory and pull keys for the ASN
            mkdir -p "keys/ases/${ASN}"
            # Using -P for port as per standard scp (user noted -p 2000+{ASN})
            scp -P "$PORT" -o StrictHostKeyChecking=no -i ./keys/master/id_rsa "root@localhost:./.ssh/id_rsa*" "./keys/ases/${ASN}/"

            # 2. Create inventory directory
            mkdir -p "inventories/${ASN}"

            # 3. Generate hosts list from templates/ips.csv
            TMP_HOSTS=$(mktemp)
            while IFS= read -r line || [ -n "$line" ]; do
                # Strip trailing comma and replace {ASN} with raw ASN value for IP
                IP=$(echo "$line" | sed "s/{ASN}/${ASN_VAL}/g" | sed 's/,$//')
                if [ -n "$IP" ]; then
                    echo "      - url: ssh://root@${IP}" >> "$TMP_HOSTS"
                fi
            done < templates/ips.csv

            # 4. Create inventory.yml by filling in the template
            INV_FILE="inventories/${ASN}/inventory.yml"

            # Replace {ASN} with padded version and adjust keyfile path to include 'ases/'
            sed "s/{ASN}/${ASN}/g" templates/inventory.yml | \
            sed "s|keyfile: ./keys/${ASN}/id_rsa|keyfile: ./keys/ases/${ASN}/id_rsa|g" > "$INV_FILE"

            # Replace the placeholder line with the actual list of hosts
            # Targets the line: '      - url: ssh://root@{IP}'
            sed -i "/{IP}/r $TMP_HOSTS" "$INV_FILE"
            sed -i "/{IP}/d" "$INV_FILE"

            rm "$TMP_HOSTS"
        fi
    done
done

echo "Done!"
